import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "restaurant.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    db = get_db()
    db.executescript("""
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
            unidad_compra TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER NOT NULL,
            equivalencia REAL NOT NULL,
            unidad_uso TEXT NOT NULL,
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
            cts REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS produccion_empleado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plato_id INTEGER NOT NULL UNIQUE,
            minutos_por_plato REAL NOT NULL,
            dias_laborables INTEGER NOT NULL,
            horas_por_dia REAL NOT NULL,
            productividad INTEGER NOT NULL CHECK(productividad BETWEEN 1 AND 100),
            FOREIGN KEY (plato_id) REFERENCES platos(id)
        );
        CREATE TABLE IF NOT EXISTS costos_indirectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gastos_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gastos_ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL
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
    """)
    db.commit()

    # Seed only if tables are empty
    count = db.execute("SELECT COUNT(*) FROM platos").fetchone()[0]
    if count > 0:
        db.close()
        return

    # Platos (7)
    platos = [
        ("Lomo Saltado", "1 porción individual", "lomo_saltado.png"),
        ("Ají de Gallina", "1 porción individual", "aji_de_gallina.png"),
        ("Ceviche Clásico", "1 porción individual", "ceviche_clasico.png"),
        ("Arroz con Leche", "1 postre individual", "arroz_con_leche.png"),
        ("Pollo a la Brasa (1/4)", "1 porción con guarnición", "pollo_brasa.png"),
        ("Causa Limeña", "1 porción individual", "causa_limena.png"),
        ("Tacu Tacu", "1 porción individual", "tacu_tacu.png"),
    ]
    db.executemany("INSERT INTO platos (nombre, descripcion, imagen) VALUES (?,?,?)", platos)

    # Ingredientes
    ingredientes = [
        ("Lomo de res", 38.00, "kg"),
        ("Pollo entero", 9.50, "kg"),
        ("Pescado fresco (corvina)", 22.00, "kg"),
        ("Papa amarilla", 3.20, "kg"),
        ("Cebolla roja", 2.50, "kg"),
        ("Tomate", 2.80, "kg"),
        ("Ají amarillo", 6.00, "kg"),
        ("Ají limo", 8.00, "kg"),
        ("Limón", 4.00, "kg"),
        ("Arroz", 3.50, "kg"),
        ("Aceite vegetal", 8.00, "litro"),
        ("Sillao (soya)", 7.50, "litro"),
        ("Leche evaporada", 3.80, "litro"),
        ("Pan de molde", 5.50, "kg"),
        ("Ajo molido", 12.00, "kg"),
        ("Culantro fresco", 4.00, "kg"),
        ("Azúcar blanca", 2.80, "kg"),
        ("Canela en rama", 18.00, "kg"),
        ("Sal de mesa", 1.50, "kg"),
        ("Papas fritas", 7.00, "kg"),
        ("Choclo (mazorca)", 3.50, "kg"),
        ("Atún en lata", 12.00, "kg"),
        ("Mayonesa", 9.00, "kg"),
        ("Frijoles cocidos", 5.50, "kg"),
    ]
    db.executemany("INSERT INTO ingredientes (nombre, costo_compra, unidad_compra) VALUES (?,?,?)", ingredientes)

    # Conversiones (all kg->g or litro->ml)
    conversiones = [
        (1, 1000, "g"), (2, 1000, "g"), (3, 1000, "g"), (4, 1000, "g"),
        (5, 1000, "g"), (6, 1000, "g"), (7, 1000, "g"), (8, 1000, "g"),
        (9, 1000, "g"), (10, 1000, "g"), (11, 1000, "ml"), (12, 1000, "ml"),
        (13, 1000, "ml"), (14, 1000, "g"), (15, 1000, "g"), (16, 1000, "g"),
        (17, 1000, "g"), (18, 1000, "g"), (19, 1000, "g"), (20, 1000, "g"),
        (21, 1000, "g"), (22, 1000, "g"), (23, 1000, "g"), (24, 1000, "g"),
    ]
    db.executemany("INSERT INTO conversiones (ingrediente_id, equivalencia, unidad_uso) VALUES (?,?,?)", conversiones)

    # Recetas: plato_id, ingrediente_id, cantidad_uso, unidad_uso
    recetas = [
        # Lomo Saltado (1)
        (1,1,200,"g"),(1,4,150,"g"),(1,5,80,"g"),(1,6,100,"g"),
        (1,12,30,"ml"),(1,11,20,"ml"),(1,15,10,"g"),(1,19,5,"g"),
        (1,10,150,"g"),(1,20,120,"g"),(1,16,10,"g"),(1,7,30,"g"),
        # Ají de Gallina (2)
        (2,2,250,"g"),(2,14,80,"g"),(2,13,150,"ml"),(2,7,60,"g"),
        (2,5,60,"g"),(2,15,10,"g"),(2,11,20,"ml"),(2,4,200,"g"),
        (2,10,150,"g"),(2,19,5,"g"),(2,16,15,"g"),
        # Ceviche Clásico (3)
        (3,3,300,"g"),(3,9,150,"g"),(3,5,100,"g"),(3,8,20,"g"),
        (3,16,10,"g"),(3,15,5,"g"),(3,19,5,"g"),(3,4,150,"g"),(3,21,100,"g"),
        # Arroz con Leche (4)
        (4,10,80,"g"),(4,13,300,"ml"),(4,17,60,"g"),(4,18,5,"g"),(4,19,2,"g"),
        # Pollo a la Brasa (5)
        (5,2,400,"g"),(5,15,15,"g"),(5,11,30,"ml"),(5,19,8,"g"),
        (5,4,200,"g"),(5,10,150,"g"),(5,7,40,"g"),(5,16,10,"g"),
        # Causa Limeña (6)
        (6,4,300,"g"),(6,9,50,"g"),(6,7,15,"g"),(6,11,20,"ml"),
        (6,22,150,"g"),(6,23,40,"g"),(6,19,3,"g"),
        # Tacu Tacu (7)
        (7,10,200,"g"),(7,24,150,"g"),(7,11,30,"ml"),(7,15,5,"g"),
        (7,5,50,"g"),(7,19,3,"g"),
    ]
    db.executemany("INSERT INTO recetas (plato_id, ingrediente_id, cantidad_uso, unidad_uso) VALUES (?,?,?,?)", recetas)

    # Empleados (from image - kitchen + admin staff)
    empleados = [
        # Kitchen
        ("Chef Principal", "Cocina", 1800, 150, 500, 162, 150),
        ("Cocinero", "Cocina", 1500, 124, 0, 135, 125),
        ("Ayudante de Cocina", "Cocina", 1200, 100, 0, 108, 100),
        ("Lavaplatos", "Cocina", 1130, 94, 0, 101.7, 94),
        # Admin
        ("Personal ADM.", "Administración", 3000, 250, 0, 270, 250),
        ("Contador", "Administración", 2500, 208, 0, 225, 208),
        ("Cajero", "Ventas", 1200, 100, 0, 108, 100),
        ("Mozo 1", "Ventas", 1130, 94, 0, 101.7, 94),
        ("Mozo 2", "Ventas", 1130, 94, 0, 101.7, 94),
        ("Vigilancia", "Seguridad", 1200, 100, 0, 108, 100),
    ]
    db.executemany(
        "INSERT INTO empleados (nombre, cargo, sueldo_base, gratificaciones, bonificaciones, seguro, cts) VALUES (?,?,?,?,?,?,?)",
        empleados
    )

    # Producción empleado (MOD params per plato)
    produccion = [
        (1, 20, 26, 10, 85),  # Lomo Saltado
        (2, 25, 26, 10, 85),  # Ají de Gallina
        (3, 15, 26, 10, 90),  # Ceviche Clásico
        (4, 10, 26, 10, 90),  # Arroz con Leche
        (5, 30, 26, 10, 85),  # Pollo a la Brasa
        (6, 18, 26, 10, 85),  # Causa Limeña
        (7, 22, 26, 10, 85),  # Tacu Tacu
    ]
    db.executemany(
        "INSERT INTO produccion_empleado (plato_id, minutos_por_plato, dias_laborables, horas_por_dia, productividad) VALUES (?,?,?,?,?)",
        produccion
    )

    # Proyección de demanda
    proyeccion = [
        (1, 80, 38.00),
        (2, 70, 28.00),
        (3, 90, 35.00),
        (4, 60, 12.00),
        (5, 45, 30.00),
        (6, 55, 25.00),
        (7, 50, 22.00),
    ]
    db.executemany(
        "INSERT INTO proyeccion (plato_id, cantidad_mensual, precio_referencial) VALUES (?,?,?)",
        proyeccion
    )

    # CIF conceptos
    cif = [
        ("Luz", 420.00),
        ("Agua", 130.00),
        ("Gas / GLP", 380.00),
        ("Alquiler local", 2500.00),
        ("Mantenimiento cocina", 150.00),
    ]
    db.executemany("INSERT INTO costos_indirectos (concepto, monto) VALUES (?,?)", cif)

    # Activos fijos
    activos = [
        ("Cocina industrial", 6500.00, 500.00, 10, "2020-01-01", "LINEAL", 1),
        ("Horno combinado", 5200.00, 400.00, 10, "2020-01-01", "LINEAL", 1),
        ("Cámara frigorífica", 4800.00, 300.00, 10, "2020-01-01", "LINEAL", 1),
        ("Freidora industrial", 1800.00, 200.00, 7, "2021-01-01", "LINEAL", 1),
        ("Menaje y utensilios", 1200.00, 0.00, 5, "2022-01-01", "LINEAL", 1),
    ]
    db.executemany(
        "INSERT INTO activos_fijos (nombre, valor_adquisicion, valor_residual, vida_util_anos, fecha_adquisicion, metodo, activo) VALUES (?,?,?,?,?,?,?)",
        activos
    )

    # Gastos admin
    ga = [("Contador", 350.00), ("Internet y teléfono", 120.00), ("Licencias y permisos", 80.00)]
    db.executemany("INSERT INTO gastos_admin (concepto, monto) VALUES (?,?)", ga)

    # Gastos ventas
    gv = [("Publicidad en redes", 250.00), ("Empaques y envases", 200.00), ("Delivery / comisión plataformas", 300.00)]
    db.executemany("INSERT INTO gastos_ventas (concepto, monto) VALUES (?,?)", gv)

    # Gastos financieros
    gf = [("Interés préstamo equipos", 180.00), ("Comisión POS bancario", 60.00)]
    db.executemany("INSERT INTO gastos_financieros (concepto, monto) VALUES (?,?)", gf)

    # Kardex entradas iniciales
    kardex_entries = [
        (1, "2025-01-01", "ENTRADA", 5, "kg", 38.00, 190.00, 5, 190.00),
        (2, "2025-01-01", "ENTRADA", 8, "kg", 9.50, 76.00, 8, 76.00),
        (3, "2025-01-01", "ENTRADA", 6, "kg", 22.00, 132.00, 6, 132.00),
        (4, "2025-01-01", "ENTRADA", 10, "kg", 3.20, 32.00, 10, 32.00),
        (10, "2025-01-01", "ENTRADA", 10, "kg", 3.50, 35.00, 10, 35.00),
        (11, "2025-01-01", "ENTRADA", 5, "litro", 8.00, 40.00, 5, 40.00),
        (13, "2025-01-01", "ENTRADA", 6, "litro", 3.80, 22.80, 6, 22.80),
        (5, "2025-01-01", "ENTRADA", 5, "kg", 2.50, 12.50, 5, 12.50),
        (7, "2025-01-01", "ENTRADA", 3, "kg", 6.00, 18.00, 3, 18.00),
    ]
    db.executemany(
        "INSERT INTO kardex (ingrediente_id, fecha, tipo, cantidad, unidad, costo_unitario, costo_total, saldo_cantidad, saldo_valor) VALUES (?,?,?,?,?,?,?,?,?)",
        kardex_entries
    )

    db.commit()
    db.close()


# ─── Calculation helpers ───────────────────────────────────────────────────────

def calcular_depreciacion_mensual(db):
    activos = db.execute("SELECT * FROM activos_fijos WHERE activo = 1").fetchall()
    total = 0
    detalle = []
    for a in activos:
        dep_anual = (a["valor_adquisicion"] - a["valor_residual"]) / a["vida_util_anos"]
        dep_mensual = dep_anual / 12
        total += dep_mensual
        detalle.append({**dict(a), "dep_anual": dep_anual, "dep_mensual": dep_mensual})
    return round(total, 4), detalle


def calcular_pct_participacion(db):
    rows = db.execute("SELECT plato_id, cantidad_mensual FROM proyeccion").fetchall()
    total_cantidad = sum(r["cantidad_mensual"] for r in rows)
    if total_cantidad == 0:
        return {}
    return {r["plato_id"]: r["cantidad_mensual"] / total_cantidad for r in rows}


def depreciacion_por_plato(db, pct, cantidad_mensual):
    total_dep, _ = calcular_depreciacion_mensual(db)
    if cantidad_mensual == 0:
        return 0
    return round((total_dep * pct) / cantidad_mensual, 4)


def cif_por_plato(db, plato_id):
    pcts = calcular_pct_participacion(db)
    pct = pcts.get(plato_id, 0)
    row = db.execute("SELECT cantidad_mensual FROM proyeccion WHERE plato_id = ?", (plato_id,)).fetchone()
    if not row or row["cantidad_mensual"] == 0:
        return 0, []
    cantidad = row["cantidad_mensual"]
    conceptos = db.execute("SELECT * FROM costos_indirectos").fetchall()
    detalle = []
    total = 0
    for c in conceptos:
        valor = round((c["monto"] * pct) / cantidad, 4)
        total += valor
        detalle.append({"concepto": c["concepto"], "monto": c["monto"], "valor_plato": valor})
    dep = depreciacion_por_plato(db, pct, cantidad)
    detalle.append({"concepto": "Depreciación activos", "monto": None, "valor_plato": dep})
    total += dep
    return round(total, 4), detalle


def mod_por_plato(db, plato_id):
    prod = db.execute("SELECT * FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()
    if not prod:
        return 0, 0
    planilla = db.execute(
        "SELECT SUM(sueldo_base+gratificaciones+bonificaciones+seguro+cts) AS total FROM empleados"
    ).fetchone()["total"] or 0
    tiempo_base = prod["dias_laborables"] * prod["horas_por_dia"] * 60
    tiempo_efectivo = tiempo_base * (prod["productividad"] / 100)
    if tiempo_efectivo == 0:
        return 0, 0
    costo_minuto = round(planilla / tiempo_efectivo, 6)
    mod = round(costo_minuto * prod["minutos_por_plato"], 4)
    return mod, costo_minuto


def mp_por_plato(db, plato_id):
    recetas = db.execute("""
        SELECT r.cantidad_uso, r.unidad_uso, i.costo_compra, i.unidad_compra, i.nombre,
               c.equivalencia
        FROM recetas r
        JOIN ingredientes i ON r.ingrediente_id = i.id
        LEFT JOIN conversiones c ON c.ingrediente_id = i.id
        WHERE r.plato_id = ?
    """, (plato_id,)).fetchall()
    detalle = []
    total = 0
    for r in recetas:
        equiv = r["equivalencia"] if r["equivalencia"] else 1
        costo_unit_real = r["costo_compra"] / equiv
        costo_total_ing = round(costo_unit_real * r["cantidad_uso"], 4)
        total += costo_total_ing
        detalle.append({
            "ingrediente": r["nombre"],
            "cantidad_uso": r["cantidad_uso"],
            "unidad_uso": r["unidad_uso"],
            "costo_compra": r["costo_compra"],
            "unidad_compra": r["unidad_compra"],
            "costo_total": costo_total_ing,
        })
    return round(total, 4), detalle


def gastos_por_plato(db, tabla, plato_id):
    pcts = calcular_pct_participacion(db)
    pct = pcts.get(plato_id, 0)
    row = db.execute("SELECT cantidad_mensual FROM proyeccion WHERE plato_id = ?", (plato_id,)).fetchone()
    if not row or row["cantidad_mensual"] == 0:
        return 0, []
    cantidad = row["cantidad_mensual"]
    conceptos = db.execute(f"SELECT * FROM {tabla}").fetchall()
    detalle = []
    total = 0
    for c in conceptos:
        valor = round((c["monto"] * pct) / cantidad, 4)
        total += valor
        detalle.append({"concepto": c["concepto"], "monto": c["monto"], "valor_plato": valor})
    return round(total, 4), detalle
