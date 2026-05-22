import os
import sqlite3


DB_PATH = os.path.join(os.path.dirname(__file__), "restaurant.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(db, table):
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(db, table, column_sql):
    column = column_sql.split()[0]
    if column not in _table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")


def _exists(db, table, where, params):
    return db.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params).fetchone() is not None


def _insert_if_missing(db, table, where, params, columns, values):
    if not _exists(db, table, where, params):
        placeholders = ",".join("?" for _ in columns)
        db.execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
            values,
        )


def migrate_schema(db):
    _add_column(db, "ingredientes", "unidad_medida TEXT NOT NULL DEFAULT 'kg'")
    _add_column(db, "ingredientes", "rendimiento REAL")
    _add_column(db, "conversiones", "factor_conversion REAL NOT NULL DEFAULT 1")
    _add_column(
        db,
        "empleados",
        "clasificacion TEXT NOT NULL DEFAULT 'MOD' CHECK(clasificacion IN ('MOD','MOI','ADMIN','VENTAS'))",
    )
    _add_column(db, "produccion_empleado", "usar_tiempo_real INTEGER DEFAULT 0")
    _add_column(
        db,
        "costos_indirectos",
        "categoria TEXT DEFAULT 'GENERAL' CHECK(categoria IN ('SERVICIO','TASA_MUNICIPAL','GENERAL'))",
    )
    _add_column(db, "costos_indirectos", "prioridad INTEGER DEFAULT 0")
    _add_column(
        db,
        "gastos_admin",
        "categoria TEXT DEFAULT 'GENERAL' CHECK(categoria IN ('GENERAL','REGULATORIO','SERVICIOS_TERCEROS'))",
    )
    _add_column(db, "gastos_ventas", "categoria TEXT DEFAULT 'GENERAL'")

    db.execute("UPDATE ingredientes SET unidad_medida = COALESCE(NULLIF(unidad_medida,''), unidad_compra)")
    db.execute(
        """
        UPDATE ingredientes
        SET rendimiento = COALESCE(
            rendimiento,
            (SELECT equivalencia FROM conversiones WHERE conversiones.ingrediente_id = ingredientes.id LIMIT 1),
            CASE WHEN unidad_compra = 'unidad' THEN 1 ELSE 1000 END
        )
        """
    )
    db.execute("UPDATE conversiones SET factor_conversion = COALESCE(NULLIF(factor_conversion, 0), equivalencia)")
    db.execute(
        """
        UPDATE empleados
        SET clasificacion = CASE
            WHEN lower(nombre) LIKE '%chef%' OR lower(nombre) LIKE '%cocinero%' OR lower(nombre) LIKE '%ayudante%' THEN 'MOD'
            WHEN lower(nombre) LIKE '%admin%' OR lower(nombre) LIKE '%contador%' OR lower(cargo) LIKE '%administr%' THEN 'ADMIN'
            WHEN lower(nombre) LIKE '%community%' OR lower(cargo) LIKE '%marketing%' THEN 'VENTAS'
            ELSE 'MOI'
        END
        WHERE clasificacion IS NULL OR clasificacion = '' OR clasificacion = 'MOD'
        """
    )
    db.execute("UPDATE costos_indirectos SET categoria='SERVICIO' WHERE lower(concepto) IN ('luz','agua','gas / glp')")
    db.execute("UPDATE costos_indirectos SET categoria='GENERAL' WHERE categoria IS NULL OR categoria = ''")
    db.execute("UPDATE costos_indirectos SET prioridad=1 WHERE lower(concepto)='gas / glp'")
    db.execute("UPDATE gastos_admin SET categoria='GENERAL' WHERE categoria IS NULL OR categoria = ''")
    db.execute("UPDATE gastos_ventas SET categoria='GENERAL' WHERE categoria IS NULL OR categoria = ''")
    db.execute(
        """
        UPDATE activos_fijos
        SET activo = 0
        WHERE nombre = 'Camara frigorifica'
          AND EXISTS (
            SELECT 1 FROM activos_fijos a2
            WHERE a2.nombre LIKE 'C%mara frigor%fica'
              AND a2.nombre <> 'Camara frigorifica'
              AND a2.activo = 1
          )
        """
    )


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS platos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            imagen TEXT
        );
        CREATE TABLE IF NOT EXISTS ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            costo_compra REAL NOT NULL,
            unidad_compra TEXT NOT NULL,
            unidad_medida TEXT NOT NULL DEFAULT 'kg',
            rendimiento REAL
        );
        CREATE TABLE IF NOT EXISTS conversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER NOT NULL,
            equivalencia REAL NOT NULL,
            unidad_uso TEXT NOT NULL,
            factor_conversion REAL NOT NULL DEFAULT 1,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes(id)
        );
        CREATE TABLE IF NOT EXISTS recetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plato_id INTEGER NOT NULL,
            ingrediente_id INTEGER NOT NULL,
            cantidad_uso REAL NOT NULL,
            unidad_uso TEXT NOT NULL,
            FOREIGN KEY (plato_id) REFERENCES platos(id),
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes(id)
        );
        CREATE TABLE IF NOT EXISTS kardex (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('ENTRADA','SALIDA','AJUSTE')),
            cantidad REAL NOT NULL,
            unidad TEXT NOT NULL,
            costo_unitario REAL NOT NULL,
            costo_total REAL NOT NULL,
            saldo_cantidad REAL NOT NULL,
            saldo_valor REAL NOT NULL,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes(id)
        );
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cargo TEXT DEFAULT '',
            sueldo_base REAL NOT NULL,
            gratificaciones REAL DEFAULT 0,
            bonificaciones REAL DEFAULT 0,
            seguro REAL DEFAULT 0,
            cts REAL DEFAULT 0,
            clasificacion TEXT NOT NULL DEFAULT 'MOD'
              CHECK(clasificacion IN ('MOD','MOI','ADMIN','VENTAS'))
        );
        CREATE TABLE IF NOT EXISTS produccion_empleado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plato_id INTEGER NOT NULL UNIQUE,
            minutos_por_plato REAL NOT NULL,
            dias_laborables INTEGER NOT NULL,
            horas_por_dia REAL NOT NULL,
            productividad INTEGER NOT NULL CHECK(productividad BETWEEN 1 AND 100),
            usar_tiempo_real INTEGER DEFAULT 0,
            FOREIGN KEY (plato_id) REFERENCES platos(id)
        );
        CREATE TABLE IF NOT EXISTS estudios_tiempo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plato_id INTEGER NOT NULL,
            tarea TEXT NOT NULL,
            empleado_id INTEGER,
            tiempo_observado REAL NOT NULL,
            fecha_registro TEXT NOT NULL,
            notas TEXT,
            FOREIGN KEY (plato_id) REFERENCES platos(id),
            FOREIGN KEY (empleado_id) REFERENCES empleados(id)
        );
        CREATE TABLE IF NOT EXISTS costos_indirectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            categoria TEXT DEFAULT 'GENERAL'
              CHECK(categoria IN ('SERVICIO','TASA_MUNICIPAL','GENERAL')),
            prioridad INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS gastos_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            categoria TEXT DEFAULT 'GENERAL'
              CHECK(categoria IN ('GENERAL','REGULATORIO','SERVICIOS_TERCEROS'))
        );
        CREATE TABLE IF NOT EXISTS gastos_ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            categoria TEXT DEFAULT 'GENERAL'
        );
        CREATE TABLE IF NOT EXISTS gastos_financieros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proyeccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plato_id INTEGER NOT NULL UNIQUE,
            cantidad_mensual INTEGER NOT NULL,
            precio_referencial REAL NOT NULL,
            FOREIGN KEY (plato_id) REFERENCES platos(id)
        );
        CREATE TABLE IF NOT EXISTS activos_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            valor_adquisicion REAL NOT NULL,
            valor_residual REAL NOT NULL DEFAULT 0,
            vida_util_anos INTEGER NOT NULL,
            fecha_adquisicion TEXT NOT NULL,
            metodo TEXT NOT NULL DEFAULT 'LINEAL',
            activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL,
            descripcion TEXT
        );
        """
    )
    migrate_schema(db)
    _seed(db)
    db.commit()
    db.close()


def _seed(db):
    platos = [
        ("Lomo Saltado", "1 porcion individual", "lomo_saltado.png"),
        ("Aji de Gallina", "1 porcion individual", "aji_de_gallina.png"),
        ("Ceviche Clasico", "1 porcion individual", "ceviche_clasico.png"),
        ("Arroz con Leche", "1 postre individual", "arroz_con_leche.png"),
        ("Pollo a la Brasa (1/4)", "1 porcion con guarnicion", "pollo_brasa.png"),
        ("Causa Limena", "1 porcion individual", "causa_limena.png"),
        ("Tacu Tacu", "1 porcion individual", "tacu_tacu.png"),
    ]
    for row in platos:
        _insert_if_missing(db, "platos", "nombre = ?", (row[0],), ("nombre", "descripcion", "imagen"), row)

    ingredientes = [
        ("Lomo de res", 38.00, "kg", "kg", 850),
        ("Pollo entero", 9.50, "kg", "kg", 780),
        ("Pescado fresco (corvina)", 22.00, "kg", "kg", 900),
        ("Papa amarilla", 3.20, "kg", "kg", 900),
        ("Cebolla roja", 2.50, "kg", "kg", 920),
        ("Tomate", 2.80, "kg", "kg", 930),
        ("Aji amarillo", 6.00, "kg", "kg", 850),
        ("Aji limo", 8.00, "kg", "kg", 850),
        ("Limon", 4.00, "kg", "kg", 450),
        ("Arroz", 3.50, "kg", "kg", 1000),
        ("Aceite vegetal", 8.00, "litro", "litro", 1000),
        ("Sillao (soya)", 7.50, "litro", "litro", 1000),
        ("Leche evaporada", 3.80, "litro", "litro", 1000),
        ("Pan de molde", 5.50, "kg", "kg", 950),
        ("Ajo molido", 12.00, "kg", "kg", 900),
        ("Culantro fresco", 4.00, "kg", "kg", 700),
        ("Azucar blanca", 2.80, "kg", "kg", 1000),
        ("Canela en rama", 18.00, "kg", "kg", 1000),
        ("Sal de mesa", 1.50, "kg", "kg", 1000),
        ("Papas fritas", 7.00, "kg", "kg", 1000),
        ("Choclo (mazorca)", 3.50, "kg", "kg", 650),
        ("Atun en lata", 12.00, "kg", "kg", 900),
        ("Mayonesa", 9.00, "kg", "kg", 1000),
        ("Frijoles cocidos", 5.50, "kg", "kg", 1000),
    ]
    for row in ingredientes:
        if not _exists(db, "ingredientes", "nombre = ?", (row[0],)):
            db.execute(
                "INSERT INTO ingredientes (nombre,costo_compra,unidad_compra,unidad_medida,rendimiento) VALUES (?,?,?,?,?)",
                row,
            )

    for nombre, _, unidad_compra, _, rendimiento in ingredientes:
        ing = db.execute("SELECT id FROM ingredientes WHERE nombre = ?", (nombre,)).fetchone()
        if not ing:
            continue
        unidad_uso = "ml" if unidad_compra == "litro" else "g"
        equivalencia = 1000 if unidad_compra in ("kg", "litro") else rendimiento
        _insert_if_missing(
            db,
            "conversiones",
            "ingrediente_id = ?",
            (ing["id"],),
            ("ingrediente_id", "equivalencia", "unidad_uso", "factor_conversion"),
            (ing["id"], equivalencia, unidad_uso, equivalencia),
        )

    _seed_recetas(db)
    _seed_empleados(db)
    _seed_produccion(db)
    _seed_proyeccion(db)
    _seed_cif(db)
    _seed_activos(db)
    _seed_gastos(db)
    _seed_kardex(db)
    _seed_configuracion(db)
    _seed_estudios_tiempo(db)


def _id(db, table, name):
    row = db.execute(f"SELECT id FROM {table} WHERE nombre = ?", (name,)).fetchone()
    return row["id"] if row else None


def _seed_recetas(db):
    nombres_platos = ["Lomo Saltado", "Aji de Gallina", "Ceviche Clasico", "Arroz con Leche", "Pollo a la Brasa (1/4)", "Causa Limena", "Tacu Tacu"]
    if db.execute("SELECT COUNT(*) FROM recetas").fetchone()[0] > 0:
        return
    p = {n: _id(db, "platos", n) for n in nombres_platos}
    i = {row["nombre"]: row["id"] for row in db.execute("SELECT id,nombre FROM ingredientes")}
    recetas = [
        (p["Lomo Saltado"], i["Lomo de res"], 200, "g"), (p["Lomo Saltado"], i["Papa amarilla"], 150, "g"),
        (p["Lomo Saltado"], i["Cebolla roja"], 80, "g"), (p["Lomo Saltado"], i["Tomate"], 100, "g"),
        (p["Lomo Saltado"], i["Sillao (soya)"], 30, "ml"), (p["Lomo Saltado"], i["Aceite vegetal"], 20, "ml"),
        (p["Lomo Saltado"], i["Ajo molido"], 10, "g"), (p["Lomo Saltado"], i["Sal de mesa"], 5, "g"),
        (p["Lomo Saltado"], i["Arroz"], 150, "g"), (p["Lomo Saltado"], i["Papas fritas"], 120, "g"),
        (p["Lomo Saltado"], i["Culantro fresco"], 10, "g"), (p["Lomo Saltado"], i["Aji amarillo"], 30, "g"),
        (p["Aji de Gallina"], i["Pollo entero"], 250, "g"), (p["Aji de Gallina"], i["Pan de molde"], 80, "g"),
        (p["Aji de Gallina"], i["Leche evaporada"], 150, "ml"), (p["Aji de Gallina"], i["Aji amarillo"], 60, "g"),
        (p["Aji de Gallina"], i["Cebolla roja"], 60, "g"), (p["Aji de Gallina"], i["Ajo molido"], 10, "g"),
        (p["Aji de Gallina"], i["Aceite vegetal"], 20, "ml"), (p["Aji de Gallina"], i["Papa amarilla"], 200, "g"),
        (p["Aji de Gallina"], i["Arroz"], 150, "g"), (p["Aji de Gallina"], i["Sal de mesa"], 5, "g"),
        (p["Aji de Gallina"], i["Culantro fresco"], 15, "g"), (p["Ceviche Clasico"], i["Pescado fresco (corvina)"], 300, "g"),
        (p["Ceviche Clasico"], i["Limon"], 150, "g"), (p["Ceviche Clasico"], i["Cebolla roja"], 100, "g"),
        (p["Ceviche Clasico"], i["Aji limo"], 20, "g"), (p["Ceviche Clasico"], i["Culantro fresco"], 10, "g"),
        (p["Ceviche Clasico"], i["Ajo molido"], 5, "g"), (p["Ceviche Clasico"], i["Sal de mesa"], 5, "g"),
        (p["Ceviche Clasico"], i["Papa amarilla"], 150, "g"), (p["Ceviche Clasico"], i["Choclo (mazorca)"], 100, "g"),
        (p["Arroz con Leche"], i["Arroz"], 80, "g"), (p["Arroz con Leche"], i["Leche evaporada"], 300, "ml"),
        (p["Arroz con Leche"], i["Azucar blanca"], 60, "g"), (p["Arroz con Leche"], i["Canela en rama"], 5, "g"),
        (p["Arroz con Leche"], i["Sal de mesa"], 2, "g"), (p["Pollo a la Brasa (1/4)"], i["Pollo entero"], 400, "g"),
        (p["Pollo a la Brasa (1/4)"], i["Ajo molido"], 15, "g"), (p["Pollo a la Brasa (1/4)"], i["Aceite vegetal"], 30, "ml"),
        (p["Pollo a la Brasa (1/4)"], i["Sal de mesa"], 8, "g"), (p["Pollo a la Brasa (1/4)"], i["Papa amarilla"], 200, "g"),
        (p["Pollo a la Brasa (1/4)"], i["Arroz"], 150, "g"), (p["Pollo a la Brasa (1/4)"], i["Aji amarillo"], 40, "g"),
        (p["Pollo a la Brasa (1/4)"], i["Culantro fresco"], 10, "g"), (p["Causa Limena"], i["Papa amarilla"], 300, "g"),
        (p["Causa Limena"], i["Limon"], 50, "g"), (p["Causa Limena"], i["Aji amarillo"], 15, "g"),
        (p["Causa Limena"], i["Aceite vegetal"], 20, "ml"), (p["Causa Limena"], i["Atun en lata"], 150, "g"),
        (p["Causa Limena"], i["Mayonesa"], 40, "g"), (p["Causa Limena"], i["Sal de mesa"], 3, "g"),
        (p["Tacu Tacu"], i["Arroz"], 200, "g"), (p["Tacu Tacu"], i["Frijoles cocidos"], 150, "g"),
        (p["Tacu Tacu"], i["Aceite vegetal"], 30, "ml"), (p["Tacu Tacu"], i["Ajo molido"], 5, "g"),
        (p["Tacu Tacu"], i["Cebolla roja"], 50, "g"), (p["Tacu Tacu"], i["Sal de mesa"], 3, "g"),
    ]
    db.executemany("INSERT INTO recetas (plato_id,ingrediente_id,cantidad_uso,unidad_uso) VALUES (?,?,?,?)", recetas)


def _seed_empleados(db):
    empleados = [
        ("Chef Principal", "Cocina", 1800, 150, 500, 162, 150, "MOD"),
        ("Cocinero", "Cocina", 1500, 124, 0, 135, 125, "MOD"),
        ("Ayudante de Cocina", "Cocina", 1200, 100, 0, 108, 100, "MOD"),
        ("Lavaplatos", "Cocina", 1130, 94, 0, 101.7, 94, "MOI"),
        ("Mozo principal", "Salon", 1250, 100, 0, 112.5, 100, "MOI"),
        ("Cajero", "Caja", 1200, 100, 0, 108, 100, "MOI"),
        ("Administrador", "Administracion", 3000, 250, 0, 270, 250, "ADMIN"),
        ("Contador", "Administracion", 2500, 208, 0, 225, 208, "ADMIN"),
        ("Community Manager", "Marketing", 1500, 125, 0, 135, 125, "VENTAS"),
        ("Vigilancia", "Seguridad", 1200, 100, 0, 108, 100, "MOI"),
    ]
    for row in empleados:
        _insert_if_missing(
            db,
            "empleados",
            "nombre = ?",
            (row[0],),
            ("nombre", "cargo", "sueldo_base", "gratificaciones", "bonificaciones", "seguro", "cts", "clasificacion"),
            row,
        )
    for nombre, clasificacion in [("Chef Principal", "MOD"), ("Cocinero", "MOD"), ("Ayudante de Cocina", "MOD"), ("Cajero", "MOI"), ("Contador", "ADMIN"), ("Administrador", "ADMIN"), ("Community Manager", "VENTAS")]:
        db.execute("UPDATE empleados SET clasificacion=? WHERE nombre=?", (clasificacion, nombre))


def _seed_produccion(db):
    rows = [(1, 20, 26, 10, 85, 0), (2, 25, 26, 10, 85, 0), (3, 15, 26, 10, 90, 0), (4, 10, 26, 10, 90, 0), (5, 30, 26, 10, 85, 0), (6, 18, 26, 10, 85, 0), (7, 22, 26, 10, 85, 0)]
    for row in rows:
        _insert_if_missing(db, "produccion_empleado", "plato_id = ?", (row[0],), ("plato_id", "minutos_por_plato", "dias_laborables", "horas_por_dia", "productividad", "usar_tiempo_real"), row)


def _seed_proyeccion(db):
    rows = [(1, 80, 38.00), (2, 70, 28.00), (3, 90, 35.00), (4, 60, 12.00), (5, 45, 30.00), (6, 55, 25.00), (7, 50, 22.00)]
    for row in rows:
        _insert_if_missing(db, "proyeccion", "plato_id = ?", (row[0],), ("plato_id", "cantidad_mensual", "precio_referencial"), row)


def _seed_cif(db):
    rows = [
        ("Luz", 420.00, "SERVICIO", 0),
        ("Agua", 130.00, "SERVICIO", 0),
        ("Gas / GLP", 380.00, "SERVICIO", 1),
        ("Alquiler local", 2500.00, "GENERAL", 0),
        ("Mantenimiento cocina", 150.00, "GENERAL", 0),
        ("Derecho produccion municipal", 120.00, "TASA_MUNICIPAL", 0),
        ("Estacionamiento", 90.00, "TASA_MUNICIPAL", 0),
    ]
    for row in rows:
        _insert_if_missing(db, "costos_indirectos", "concepto = ?", (row[0],), ("concepto", "monto", "categoria", "prioridad"), row)
        db.execute("UPDATE costos_indirectos SET categoria=?, prioridad=? WHERE concepto=?", (row[2], row[3], row[0]))


def _seed_activos(db):
    rows = [
        ("Cocina industrial", 6500.00, 500.00, 10, "2020-01-01", "LINEAL", 1),
        ("Horno combinado", 5200.00, 400.00, 10, "2020-01-01", "LINEAL", 1),
        ("Camara frigorifica", 4800.00, 300.00, 10, "2020-01-01", "LINEAL", 1),
        ("Freidora industrial", 1800.00, 200.00, 7, "2021-01-01", "LINEAL", 1),
        ("Menaje y utensilios", 1200.00, 0.00, 5, "2022-01-01", "LINEAL", 1),
    ]
    for row in rows:
        if row[0] == "Camara frigorifica" and db.execute("SELECT 1 FROM activos_fijos WHERE nombre LIKE 'C%mara frigor%fica' LIMIT 1").fetchone():
            continue
        _insert_if_missing(db, "activos_fijos", "nombre = ?", (row[0],), ("nombre", "valor_adquisicion", "valor_residual", "vida_util_anos", "fecha_adquisicion", "metodo", "activo"), row)


def _seed_gastos(db):
    ga = [
        ("Contador", 350.00, "GENERAL"),
        ("Internet y telefono", 120.00, "GENERAL"),
        ("Licencias y permisos", 80.00, "GENERAL"),
        ("Utiles de escritorio", 60.00, "GENERAL"),
        ("Energia area administrativa", 45.00, "GENERAL"),
        ("Inspeccion MINSA / SENASA", 120.00, "REGULATORIO"),
        ("Inspeccion OEFA / Defensa Civil", 90.00, "REGULATORIO"),
        ("Fiscalizacion Municipal", 80.00, "REGULATORIO"),
    ]
    for row in ga:
        _insert_if_missing(db, "gastos_admin", "concepto = ?", (row[0],), ("concepto", "monto", "categoria"), row)
        db.execute("UPDATE gastos_admin SET categoria=? WHERE concepto=?", (row[2], row[0]))
    gv = [("Publicidad en redes", 250.00, "GENERAL"), ("Empaques y envases", 200.00, "GENERAL"), ("Delivery / comision plataformas", 300.00, "GENERAL")]
    for row in gv:
        _insert_if_missing(db, "gastos_ventas", "concepto = ?", (row[0],), ("concepto", "monto", "categoria"), row)
    gf = [("Interes prestamo equipos", 180.00), ("Comision POS bancario", 60.00)]
    for row in gf:
        _insert_if_missing(db, "gastos_financieros", "concepto = ?", (row[0],), ("concepto", "monto"), row)


def _seed_kardex(db):
    if db.execute("SELECT COUNT(*) FROM kardex").fetchone()[0] > 0:
        return
    rows = [(1, "2025-01-01", "ENTRADA", 5, "kg", 38.00, 190.00, 5, 190.00), (2, "2025-01-01", "ENTRADA", 8, "kg", 9.50, 76.00, 8, 76.00), (3, "2025-01-01", "ENTRADA", 6, "kg", 22.00, 132.00, 6, 132.00), (4, "2025-01-01", "ENTRADA", 10, "kg", 3.20, 32.00, 10, 32.00), (10, "2025-01-01", "ENTRADA", 10, "kg", 3.50, 35.00, 10, 35.00), (11, "2025-01-01", "ENTRADA", 5, "litro", 8.00, 40.00, 5, 40.00), (13, "2025-01-01", "ENTRADA", 6, "litro", 3.80, 22.80, 6, 22.80), (5, "2025-01-01", "ENTRADA", 5, "kg", 2.50, 12.50, 5, 12.50), (7, "2025-01-01", "ENTRADA", 3, "kg", 6.00, 18.00, 3, 18.00)]
    db.executemany("INSERT INTO kardex (ingrediente_id,fecha,tipo,cantidad,unidad,costo_unitario,costo_total,saldo_cantidad,saldo_valor) VALUES (?,?,?,?,?,?,?,?,?)", rows)


def _seed_configuracion(db):
    rows = [
        ("nombre_negocio", "Mi Restaurante", "Nombre del negocio"),
        ("igv_pct", "10", "Porcentaje de IGV"),
        ("moneda", "PEN", "Moneda del sistema"),
        ("sector", "RESTAURANTE", "Sector del negocio"),
    ]
    for row in rows:
        _insert_if_missing(db, "configuracion", "clave = ?", (row[0],), ("clave", "valor", "descripcion"), row)


def _seed_estudios_tiempo(db):
    if db.execute("SELECT COUNT(*) FROM estudios_tiempo").fetchone()[0] > 0:
        return
    plato_id = _id(db, "platos", "Lomo Saltado")
    chef = _id(db, "empleados", "Chef Principal")
    if plato_id:
        rows = [
            (plato_id, "Preparar mise en place", chef, 6, "2025-01-01", "Corte de insumos"),
            (plato_id, "Coccion", chef, 10, "2025-01-01", "Salteado en wok"),
            (plato_id, "Emplatar", chef, 4, "2025-01-01", "Presentacion final"),
        ]
        db.executemany("INSERT INTO estudios_tiempo (plato_id,tarea,empleado_id,tiempo_observado,fecha_registro,notas) VALUES (?,?,?,?,?,?)", rows)


def calcular_depreciacion_mensual(db):
    from calculos import calcular_depreciacion_mensual as fn
    return fn(db)


def calcular_pct_participacion(db):
    from calculos import calcular_pct_participacion as fn
    return fn(db)


def depreciacion_por_plato(db, pct, cantidad_mensual):
    from calculos import depreciacion_por_plato as fn
    return fn(db, pct, cantidad_mensual)


def cif_por_plato(db, plato_id):
    from calculos import cif_por_plato as fn
    return fn(db, plato_id)


def mod_por_plato(db, plato_id):
    from calculos import mod_por_plato as fn
    return fn(db, plato_id)


def mp_por_plato(db, plato_id):
    from calculos import mp_por_plato as fn
    return fn(db, plato_id)


def gastos_por_plato(db, tabla, plato_id):
    from calculos import gastos_por_plato as fn
    return fn(db, tabla, plato_id)
