from flask import Flask, render_template, request, redirect, url_for, flash, g
import os
from database import get_db, init_db
from calculos import (
    calcular_depreciacion_mensual, calcular_pct_participacion,
    cif_por_plato, mod_por_plato, mp_por_plato, gastos_por_plato,
    calcular_planilla_por_clasificacion, obtener_configuracion,
    calcular_estado_resultados, tiempo_real_por_plato
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "restaurant-secret-2025")

PORT = int(os.environ.get("PORT", 5000))


@app.before_request
def open_db():
    g.db = get_db()


@app.teardown_request
def close_db(exc):
    db = getattr(g, "db", None)
    if db:
        db.close()


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    db = g.db
    platos = db.execute("SELECT * FROM platos").fetchall()
    pcts = calcular_pct_participacion(db)
    proj = {r["plato_id"]: r for r in db.execute("SELECT * FROM proyeccion").fetchall()}
    total_cantidad = sum(r["cantidad_mensual"] for r in proj.values())
    total_ingresos = sum(r["cantidad_mensual"] * r["precio_referencial"] for r in proj.values())

    resumen = []
    for p in platos:
        pr = proj.get(p["id"])
        if pr:
            pct = pcts.get(p["id"], 0)
            mp, _ = mp_por_plato(db, p["id"])
            mod, _ = mod_por_plato(db, p["id"])
            cif, _ = cif_por_plato(db, p["id"])
            ga, _ = gastos_por_plato(db, "gastos_admin", p["id"])
            gv, _ = gastos_por_plato(db, "gastos_ventas", p["id"])
            gf, _ = gastos_por_plato(db, "gastos_financieros", p["id"])
            costo_total = round(mp + mod + cif + ga + gv + gf, 4)
            resumen.append({
                "plato": p,
                "cantidad": pr["cantidad_mensual"],
                "precio_ref": pr["precio_referencial"],
                "ingreso": pr["cantidad_mensual"] * pr["precio_referencial"],
                "pct": round(pct * 100, 2),
                "costo_total": costo_total,
            })
    return render_template("dashboard.html", resumen=resumen,
                           total_cantidad=total_cantidad, total_ingresos=total_ingresos)


# ─── Proyección ───────────────────────────────────────────────────────────────

@app.route("/proyeccion")
def proyeccion():
    db = g.db
    platos = db.execute("SELECT * FROM platos").fetchall()
    proj = {r["plato_id"]: r for r in db.execute("SELECT * FROM proyeccion").fetchall()}
    pcts = calcular_pct_participacion(db)
    total_cantidad = sum(r["cantidad_mensual"] for r in proj.values())
    total_ingresos = sum(r["cantidad_mensual"] * r["precio_referencial"] for r in proj.values())
    return render_template("proyeccion.html", platos=platos, proj=proj, pcts=pcts,
                           total_cantidad=total_cantidad, total_ingresos=total_ingresos)


@app.route("/proyeccion/guardar", methods=["POST"])
def proyeccion_guardar():
    db = g.db
    platos = db.execute("SELECT id FROM platos").fetchall()
    for p in platos:
        pid = p["id"]
        cantidad = request.form.get(f"cantidad_{pid}", "0")
        precio = request.form.get(f"precio_{pid}", "0")
        try:
            cantidad = int(cantidad)
            precio = float(precio)
        except ValueError:
            continue
        existing = db.execute("SELECT id FROM proyeccion WHERE plato_id = ?", (pid,)).fetchone()
        if existing:
            db.execute("UPDATE proyeccion SET cantidad_mensual=?, precio_referencial=? WHERE plato_id=?",
                       (cantidad, precio, pid))
        else:
            db.execute("INSERT INTO proyeccion (plato_id, cantidad_mensual, precio_referencial) VALUES (?,?,?)",
                       (pid, cantidad, precio))
    db.commit()
    flash("Proyección guardada correctamente.", "success")
    return redirect(url_for("proyeccion"))


# ─── Platos ───────────────────────────────────────────────────────────────────

@app.route("/platos")
def platos():
    db = g.db
    platos = db.execute("SELECT * FROM platos").fetchall()
    return render_template("platos.html", platos=platos)


@app.route("/platos/nuevo", methods=["POST"])
def plato_nuevo():
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    if nombre:
        db.execute("INSERT INTO platos (nombre, descripcion) VALUES (?,?)", (nombre, descripcion))
        db.commit()
        flash("Plato creado.", "success")
    return redirect(url_for("platos"))


@app.route("/platos/editar/<int:pid>", methods=["POST"])
def plato_editar(pid):
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    db.execute("UPDATE platos SET nombre=?, descripcion=? WHERE id=?", (nombre, descripcion, pid))
    db.commit()
    flash("Plato actualizado.", "success")
    return redirect(url_for("platos"))


# ─── Ingredientes ─────────────────────────────────────────────────────────────

@app.route("/ingredientes")
def ingredientes():
    db = g.db
    items = db.execute("""
        SELECT i.*, c.equivalencia, c.unidad_uso, c.factor_conversion
        FROM ingredientes i
        LEFT JOIN conversiones c ON c.ingrediente_id = i.id
        ORDER BY i.nombre
    """).fetchall()
    return render_template("ingredientes.html", ingredientes=items)


@app.route("/ingredientes/nuevo", methods=["POST"])
def ingrediente_nuevo():
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    costo = float(request.form.get("costo_compra", 0))
    unidad = request.form.get("unidad_compra", "kg").strip()
    unidad_medida = request.form.get("unidad_medida", unidad).strip()
    rendimiento = float(request.form.get("rendimiento", 0) or 0)
    equiv = float(request.form.get("equivalencia", 1000))
    unidad_uso = request.form.get("unidad_uso", "g").strip()
    factor = float(request.form.get("factor_conversion", equiv) or equiv)
    if nombre:
        cur = db.execute("INSERT INTO ingredientes (nombre, costo_compra, unidad_compra, unidad_medida, rendimiento) VALUES (?,?,?,?,?)",
                         (nombre, costo, unidad, unidad_medida, rendimiento or equiv))
        db.execute("INSERT INTO conversiones (ingrediente_id, equivalencia, unidad_uso, factor_conversion) VALUES (?,?,?,?)",
                   (cur.lastrowid, equiv, unidad_uso, factor))
        db.commit()
        flash("Ingrediente creado.", "success")
    return redirect(url_for("ingredientes"))


@app.route("/ingredientes/editar/<int:iid>", methods=["POST"])
def ingrediente_editar(iid):
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    costo = float(request.form.get("costo_compra", 0))
    unidad = request.form.get("unidad_compra", "kg").strip()
    unidad_medida = request.form.get("unidad_medida", unidad).strip()
    rendimiento = float(request.form.get("rendimiento", 0) or 0)
    equiv = float(request.form.get("equivalencia", 1000) or 1000)
    unidad_uso = request.form.get("unidad_uso", "g").strip()
    factor = float(request.form.get("factor_conversion", equiv) or equiv)
    db.execute("UPDATE ingredientes SET nombre=?, costo_compra=?, unidad_compra=?, unidad_medida=?, rendimiento=? WHERE id=?",
               (nombre, costo, unidad, unidad_medida, rendimiento or equiv, iid))
    existing = db.execute("SELECT id FROM conversiones WHERE ingrediente_id = ?", (iid,)).fetchone()
    if existing:
        db.execute("UPDATE conversiones SET equivalencia=?, unidad_uso=?, factor_conversion=? WHERE ingrediente_id=?",
                   (equiv, unidad_uso, factor, iid))
    else:
        db.execute("INSERT INTO conversiones (ingrediente_id, equivalencia, unidad_uso, factor_conversion) VALUES (?,?,?,?)",
                   (iid, equiv, unidad_uso, factor))
    db.commit()
    flash("Ingrediente actualizado.", "success")
    return redirect(url_for("ingredientes"))


@app.route("/ingredientes/eliminar/<int:iid>", methods=["POST"])
def ingrediente_eliminar(iid):
    db = g.db
    db.execute("DELETE FROM recetas WHERE ingrediente_id = ?", (iid,))
    db.execute("DELETE FROM conversiones WHERE ingrediente_id = ?", (iid,))
    db.execute("DELETE FROM kardex WHERE ingrediente_id = ?", (iid,))
    db.execute("DELETE FROM ingredientes WHERE id = ?", (iid,))
    db.commit()
    flash("Ingrediente eliminado.", "success")
    return redirect(url_for("ingredientes"))


# ─── Recetas ──────────────────────────────────────────────────────────────────

@app.route("/recetas")
def recetas():
    db = g.db
    platos = db.execute("SELECT * FROM platos").fetchall()
    ingredientes = db.execute("SELECT * FROM ingredientes ORDER BY nombre").fetchall()
    recetas_por_plato = {}
    for p in platos:
        rows = db.execute("""
            SELECT r.id, r.cantidad_uso, r.unidad_uso, i.nombre, i.costo_compra,
                   i.unidad_compra, c.equivalencia
            FROM recetas r
            JOIN ingredientes i ON r.ingrediente_id = i.id
            LEFT JOIN conversiones c ON c.ingrediente_id = i.id
            WHERE r.plato_id = ?
        """, (p["id"],)).fetchall()
        total = 0
        items = []
        for r in rows:
            equiv = r["equivalencia"] if r["equivalencia"] else 1
            costo = round((r["costo_compra"] / equiv) * r["cantidad_uso"], 4)
            total += costo
            items.append({**dict(r), "costo_total": costo})
        recetas_por_plato[p["id"]] = {"items": items, "total": round(total, 4)}
    return render_template("recetas.html", platos=platos, ingredientes=ingredientes,
                           recetas_por_plato=recetas_por_plato)


@app.route("/recetas/nuevo", methods=["POST"])
def receta_nuevo():
    db = g.db
    plato_id = int(request.form.get("plato_id", 0))
    ingrediente_id = int(request.form.get("ingrediente_id", 0))
    cantidad = float(request.form.get("cantidad_uso", 0))
    unidad = request.form.get("unidad_uso", "g").strip()
    if plato_id and ingrediente_id and cantidad > 0:
        db.execute("INSERT INTO recetas (plato_id, ingrediente_id, cantidad_uso, unidad_uso) VALUES (?,?,?,?)",
                   (plato_id, ingrediente_id, cantidad, unidad))
        db.commit()
        flash("Ingrediente añadido a la receta.", "success")
    return redirect(url_for("recetas"))


@app.route("/recetas/editar/<int:rid>", methods=["POST"])
def receta_editar(rid):
    db = g.db
    cantidad = float(request.form.get("cantidad_uso", 0))
    unidad = request.form.get("unidad_uso", "g").strip()
    db.execute("UPDATE recetas SET cantidad_uso=?, unidad_uso=? WHERE id=?", (cantidad, unidad, rid))
    db.commit()
    flash("Receta actualizada.", "success")
    return redirect(url_for("recetas"))


@app.route("/recetas/eliminar/<int:rid>", methods=["POST"])
def receta_eliminar(rid):
    db = g.db
    db.execute("DELETE FROM recetas WHERE id = ?", (rid,))
    db.commit()
    flash("Ingrediente quitado de la receta.", "success")
    return redirect(url_for("recetas"))


# ─── Empleados ────────────────────────────────────────────────────────────────

@app.route("/empleados")
def empleados():
    db = g.db
    items = db.execute("SELECT * FROM empleados ORDER BY cargo, nombre").fetchall()
    planilla_total = sum(
        e["sueldo_base"] + e["gratificaciones"] + e["bonificaciones"] + e["seguro"] + e["cts"]
        for e in items
    )
    subtotales = calcular_planilla_por_clasificacion(db)
    return render_template("empleados.html", empleados=items, planilla_total=planilla_total,
                           subtotales=subtotales)


@app.route("/empleados/nuevo", methods=["POST"])
def empleado_nuevo():
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    cargo = request.form.get("cargo", "").strip()
    sueldo_base = float(request.form.get("sueldo_base", 0))
    gratif = float(request.form.get("gratificaciones", 0))
    bonif = float(request.form.get("bonificaciones", 0))
    seguro = float(request.form.get("seguro", 0))
    cts = float(request.form.get("cts", 0))
    clasificacion = request.form.get("clasificacion", "MOD")
    if nombre:
        db.execute("INSERT INTO empleados (nombre, cargo, sueldo_base, gratificaciones, bonificaciones, seguro, cts, clasificacion) VALUES (?,?,?,?,?,?,?,?)",
                   (nombre, cargo, sueldo_base, gratif, bonif, seguro, cts, clasificacion))
        db.commit()
        flash("Empleado registrado.", "success")
    return redirect(url_for("empleados"))


@app.route("/empleados/editar/<int:eid>", methods=["POST"])
def empleado_editar(eid):
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    cargo = request.form.get("cargo", "").strip()
    sueldo_base = float(request.form.get("sueldo_base", 0))
    gratif = float(request.form.get("gratificaciones", 0))
    bonif = float(request.form.get("bonificaciones", 0))
    seguro = float(request.form.get("seguro", 0))
    cts = float(request.form.get("cts", 0))
    clasificacion = request.form.get("clasificacion", "MOD")
    db.execute("UPDATE empleados SET nombre=?, cargo=?, sueldo_base=?, gratificaciones=?, bonificaciones=?, seguro=?, cts=?, clasificacion=? WHERE id=?",
               (nombre, cargo, sueldo_base, gratif, bonif, seguro, cts, clasificacion, eid))
    db.commit()
    flash("Empleado actualizado.", "success")
    return redirect(url_for("empleados"))


@app.route("/empleados/eliminar/<int:eid>", methods=["POST"])
def empleado_eliminar(eid):
    db = g.db
    db.execute("DELETE FROM empleados WHERE id = ?", (eid,))
    db.commit()
    flash("Empleado eliminado.", "success")
    return redirect(url_for("empleados"))


# ─── Productividad / MOD ──────────────────────────────────────────────────────

@app.route("/productividad")
def productividad():
    db = g.db
    platos = db.execute("SELECT * FROM platos").fetchall()
    prod_map = {r["plato_id"]: r for r in db.execute("SELECT * FROM produccion_empleado").fetchall()}
    subtotales = calcular_planilla_por_clasificacion(db)
    planilla_total = subtotales["MOD"]
    mod_data = []
    for p in platos:
        pr = prod_map.get(p["id"])
        mod, costo_min = mod_por_plato(db, p["id"])
        tiempo_real = tiempo_real_por_plato(db, p["id"])
        mod_data.append({"plato": p, "prod": pr, "mod": mod, "costo_min": costo_min, "tiempo_real": tiempo_real})
    return render_template("productividad.html", platos=platos, prod_map=prod_map,
                           planilla_total=planilla_total, mod_data=mod_data,
                           subtotales=subtotales)


@app.route("/productividad/guardar", methods=["POST"])
def productividad_guardar():
    db = g.db
    platos = db.execute("SELECT id FROM platos").fetchall()
    for p in platos:
        pid = p["id"]
        minutos = request.form.get(f"minutos_{pid}")
        dias = request.form.get(f"dias_{pid}")
        horas = request.form.get(f"horas_{pid}")
        prod = request.form.get(f"productividad_{pid}")
        usar_tiempo_real = 1 if request.form.get(f"usar_tiempo_real_{pid}") else 0
        if not all([minutos, dias, horas, prod]):
            continue
        try:
            minutos = float(minutos)
            dias = int(dias)
            horas = float(horas)
            prod_val = int(prod)
            if not (1 <= prod_val <= 100):
                flash(f"Productividad debe estar entre 1 y 100 para plato {pid}.", "danger")
                continue
        except ValueError:
            continue
        existing = db.execute("SELECT id FROM produccion_empleado WHERE plato_id = ?", (pid,)).fetchone()
        if existing:
            db.execute("UPDATE produccion_empleado SET minutos_por_plato=?, dias_laborables=?, horas_por_dia=?, productividad=?, usar_tiempo_real=? WHERE plato_id=?",
                       (minutos, dias, horas, prod_val, usar_tiempo_real, pid))
        else:
            db.execute("INSERT INTO produccion_empleado (plato_id, minutos_por_plato, dias_laborables, horas_por_dia, productividad, usar_tiempo_real) VALUES (?,?,?,?,?,?)",
                       (pid, minutos, dias, horas, prod_val, usar_tiempo_real))
    db.commit()
    flash("Parámetros de productividad guardados.", "success")
    return redirect(url_for("productividad"))


@app.route("/estudios-tiempo/<int:plato_id>")
def estudios_tiempo(plato_id):
    db = g.db
    plato = db.execute("SELECT * FROM platos WHERE id = ?", (plato_id,)).fetchone()
    if not plato:
        flash("Plato no encontrado.", "danger")
        return redirect(url_for("productividad"))
    empleados = db.execute("SELECT * FROM empleados ORDER BY nombre").fetchall()
    tareas = db.execute("""
        SELECT et.*, e.nombre AS empleado
        FROM estudios_tiempo et
        LEFT JOIN empleados e ON e.id = et.empleado_id
        WHERE et.plato_id = ?
        ORDER BY et.fecha_registro, et.id
    """, (plato_id,)).fetchall()
    total_tiempo = sum(t["tiempo_observado"] for t in tareas)
    prod = db.execute("SELECT * FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()
    return render_template("estudios_tiempo.html", plato=plato, empleados=empleados,
                           tareas=tareas, total_tiempo=total_tiempo, prod=prod)


@app.route("/estudios-tiempo")
def estudios_tiempo_index():
    db = g.db
    plato = db.execute("SELECT id FROM platos ORDER BY id LIMIT 1").fetchone()
    if not plato:
        flash("Primero registra un plato.", "warning")
        return redirect(url_for("platos"))
    return redirect(url_for("estudios_tiempo", plato_id=plato["id"]))


@app.route("/estudios-tiempo/<int:plato_id>/nuevo", methods=["POST"])
def estudio_tiempo_nuevo(plato_id):
    db = g.db
    tarea = request.form.get("tarea", "").strip()
    empleado_id = request.form.get("empleado_id") or None
    tiempo = float(request.form.get("tiempo_observado", 0) or 0)
    fecha = request.form.get("fecha_registro", "2025-01-01")
    notas = request.form.get("notas", "").strip()
    if tarea and tiempo > 0:
        db.execute(
            "INSERT INTO estudios_tiempo (plato_id, tarea, empleado_id, tiempo_observado, fecha_registro, notas) VALUES (?,?,?,?,?,?)",
            (plato_id, tarea, empleado_id, tiempo, fecha, notas),
        )
        db.commit()
        flash("Toma de tiempo registrada.", "success")
    return redirect(url_for("estudios_tiempo", plato_id=plato_id))


@app.route("/estudios-tiempo/<int:plato_id>/toggle", methods=["POST"])
def estudio_tiempo_toggle(plato_id):
    db = g.db
    usar = 1 if request.form.get("usar_tiempo_real") else 0
    existing = db.execute("SELECT id FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()
    if existing:
        db.execute("UPDATE produccion_empleado SET usar_tiempo_real=? WHERE plato_id=?", (usar, plato_id))
    else:
        db.execute("INSERT INTO produccion_empleado (plato_id, minutos_por_plato, dias_laborables, horas_por_dia, productividad, usar_tiempo_real) VALUES (?,?,?,?,?,?)",
                   (plato_id, 20, 26, 10, 85, usar))
    db.commit()
    flash("Modo de tiempo actualizado.", "success")
    return redirect(url_for("estudios_tiempo", plato_id=plato_id))


# ─── CIF ──────────────────────────────────────────────────────────────────────

@app.route("/costos-indirectos")
def costos_indirectos():
    db = g.db
    items = db.execute("SELECT * FROM costos_indirectos ORDER BY categoria, prioridad DESC, concepto").fetchall()
    total = sum(i["monto"] for i in items)
    subtotales = {}
    for item in items:
        subtotales[item["categoria"]] = subtotales.get(item["categoria"], 0) + item["monto"]
    total_dep, _ = calcular_depreciacion_mensual(db)
    planillas = calcular_planilla_por_clasificacion(db)
    return render_template("costos_indirectos.html", items=items, total=total,
                           subtotales=subtotales, total_dep=total_dep,
                           planilla_moi=planillas["MOI"])


@app.route("/costos-indirectos/nuevo", methods=["POST"])
def cif_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    prioridad = int(request.form.get("prioridad", 0) or 0)
    if concepto:
        db.execute("INSERT INTO costos_indirectos (concepto, monto, categoria, prioridad) VALUES (?,?,?,?)",
                   (concepto, monto, categoria, prioridad))
        db.commit()
        flash("CIF agregado.", "success")
    return redirect(url_for("costos_indirectos"))


@app.route("/costos-indirectos/editar/<int:cid>", methods=["POST"])
def cif_editar(cid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    prioridad = int(request.form.get("prioridad", 0) or 0)
    db.execute("UPDATE costos_indirectos SET concepto=?, monto=?, categoria=?, prioridad=? WHERE id=?",
               (concepto, monto, categoria, prioridad, cid))
    db.commit()
    flash("CIF actualizado.", "success")
    return redirect(url_for("costos_indirectos"))


@app.route("/costos-indirectos/eliminar/<int:cid>", methods=["POST"])
def cif_eliminar(cid):
    db = g.db
    db.execute("DELETE FROM costos_indirectos WHERE id = ?", (cid,))
    db.commit()
    flash("CIF eliminado.", "success")
    return redirect(url_for("costos_indirectos"))


# ─── Activos Fijos ────────────────────────────────────────────────────────────

@app.route("/activos-fijos")
def activos_fijos():
    db = g.db
    total_dep, detalle = calcular_depreciacion_mensual(db)
    inactivos = db.execute("SELECT * FROM activos_fijos WHERE activo = 0").fetchall()
    return render_template("activos_fijos.html", detalle=detalle, inactivos=inactivos, total_dep=total_dep)


@app.route("/activos-fijos/nuevo", methods=["POST"])
def activo_nuevo():
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    val_adq = float(request.form.get("valor_adquisicion", 0))
    val_res = float(request.form.get("valor_residual", 0))
    vida = int(request.form.get("vida_util_anos", 5))
    fecha = request.form.get("fecha_adquisicion", "2025-01-01")
    if nombre:
        db.execute("INSERT INTO activos_fijos (nombre, valor_adquisicion, valor_residual, vida_util_anos, fecha_adquisicion) VALUES (?,?,?,?,?)",
                   (nombre, val_adq, val_res, vida, fecha))
        db.commit()
        flash("Activo fijo registrado.", "success")
    return redirect(url_for("activos_fijos"))


@app.route("/activos-fijos/editar/<int:aid>", methods=["POST"])
def activo_editar(aid):
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    val_adq = float(request.form.get("valor_adquisicion", 0))
    val_res = float(request.form.get("valor_residual", 0))
    vida = int(request.form.get("vida_util_anos", 5))
    fecha = request.form.get("fecha_adquisicion", "2025-01-01")
    db.execute("UPDATE activos_fijos SET nombre=?, valor_adquisicion=?, valor_residual=?, vida_util_anos=?, fecha_adquisicion=? WHERE id=?",
               (nombre, val_adq, val_res, vida, fecha, aid))
    db.commit()
    flash("Activo actualizado.", "success")
    return redirect(url_for("activos_fijos"))


@app.route("/activos-fijos/eliminar/<int:aid>", methods=["POST"])
def activo_eliminar(aid):
    db = g.db
    db.execute("UPDATE activos_fijos SET activo = 0 WHERE id = ?", (aid,))
    db.commit()
    flash("Activo desactivado.", "success")
    return redirect(url_for("activos_fijos"))


# ─── Gastos Admin ─────────────────────────────────────────────────────────────

@app.route("/gastos-admin")
def gastos_admin():
    db = g.db
    items = db.execute("SELECT * FROM gastos_admin ORDER BY categoria, concepto").fetchall()
    total = sum(i["monto"] for i in items)
    planilla_admin = calcular_planilla_por_clasificacion(db)["ADMIN"]
    total_con_planilla = total + planilla_admin
    return render_template("gastos_admin.html", items=items, total=total,
                           planilla_admin=planilla_admin, total_con_planilla=total_con_planilla)


@app.route("/gastos-admin/nuevo", methods=["POST"])
def ga_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    if concepto:
        db.execute("INSERT INTO gastos_admin (concepto, monto, categoria) VALUES (?,?,?)",
                   (concepto, monto, categoria))
        db.commit()
        flash("Gasto administrativo agregado.", "success")
    return redirect(url_for("gastos_admin"))


@app.route("/gastos-admin/editar/<int:gid>", methods=["POST"])
def ga_editar(gid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    db.execute("UPDATE gastos_admin SET concepto=?, monto=?, categoria=? WHERE id=?",
               (concepto, monto, categoria, gid))
    db.commit()
    flash("Gasto actualizado.", "success")
    return redirect(url_for("gastos_admin"))


@app.route("/gastos-admin/eliminar/<int:gid>", methods=["POST"])
def ga_eliminar(gid):
    db = g.db
    db.execute("DELETE FROM gastos_admin WHERE id = ?", (gid,))
    db.commit()
    flash("Gasto eliminado.", "success")
    return redirect(url_for("gastos_admin"))


# ─── Gastos Ventas ────────────────────────────────────────────────────────────

@app.route("/gastos-ventas")
def gastos_ventas():
    db = g.db
    items = db.execute("SELECT * FROM gastos_ventas ORDER BY categoria, concepto").fetchall()
    total = sum(i["monto"] for i in items)
    planilla_ventas = calcular_planilla_por_clasificacion(db)["VENTAS"]
    total_con_planilla = total + planilla_ventas
    return render_template("gastos_ventas.html", items=items, total=total,
                           planilla_ventas=planilla_ventas, total_con_planilla=total_con_planilla)


@app.route("/gastos-ventas/nuevo", methods=["POST"])
def gv_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    if concepto:
        db.execute("INSERT INTO gastos_ventas (concepto, monto, categoria) VALUES (?,?,?)",
                   (concepto, monto, categoria))
        db.commit()
        flash("Gasto de ventas agregado.", "success")
    return redirect(url_for("gastos_ventas"))


@app.route("/gastos-ventas/editar/<int:gid>", methods=["POST"])
def gv_editar(gid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    categoria = request.form.get("categoria", "GENERAL")
    db.execute("UPDATE gastos_ventas SET concepto=?, monto=?, categoria=? WHERE id=?",
               (concepto, monto, categoria, gid))
    db.commit()
    flash("Gasto actualizado.", "success")
    return redirect(url_for("gastos_ventas"))


@app.route("/gastos-ventas/eliminar/<int:gid>", methods=["POST"])
def gv_eliminar(gid):
    db = g.db
    db.execute("DELETE FROM gastos_ventas WHERE id = ?", (gid,))
    db.commit()
    flash("Gasto eliminado.", "success")
    return redirect(url_for("gastos_ventas"))


# ─── Gastos Financieros ───────────────────────────────────────────────────────

@app.route("/gastos-financieros")
def gastos_financieros():
    db = g.db
    items = db.execute("SELECT * FROM gastos_financieros").fetchall()
    total = sum(i["monto"] for i in items)
    return render_template("gastos_financieros.html", items=items, total=total)


@app.route("/gastos-financieros/nuevo", methods=["POST"])
def gf_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    if concepto:
        db.execute("INSERT INTO gastos_financieros (concepto, monto) VALUES (?,?)", (concepto, monto))
        db.commit()
        flash("Gasto financiero agregado.", "success")
    return redirect(url_for("gastos_financieros"))


@app.route("/gastos-financieros/editar/<int:gid>", methods=["POST"])
def gf_editar(gid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    db.execute("UPDATE gastos_financieros SET concepto=?, monto=? WHERE id=?", (concepto, monto, gid))
    db.commit()
    flash("Gasto actualizado.", "success")
    return redirect(url_for("gastos_financieros"))


@app.route("/gastos-financieros/eliminar/<int:gid>", methods=["POST"])
def gf_eliminar(gid):
    db = g.db
    db.execute("DELETE FROM gastos_financieros WHERE id = ?", (gid,))
    db.commit()
    flash("Gasto eliminado.", "success")
    return redirect(url_for("gastos_financieros"))


@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    db = g.db
    if request.method == "POST":
        for clave in ["nombre_negocio", "igv_pct", "moneda", "sector"]:
            valor = request.form.get(clave, "").strip()
            db.execute("UPDATE configuracion SET valor=? WHERE clave=?", (valor, clave))
        db.commit()
        flash("Configuracion actualizada.", "success")
        return redirect(url_for("configuracion"))
    config = obtener_configuracion(db)
    return render_template("configuracion.html", config=config)


@app.route("/ayuda")
def ayuda():
    modulos = [
        ("Inventario", "La materia prima usa rendimiento para reflejar merma: costo unitario real = costo compra / rendimiento util."),
        ("Mano de obra", "La planilla MOD calcula costo por minuto. MOI se distribuye como CIF; ADMIN y VENTAS se suman a sus gastos."),
        ("Tiempos", "Cada plato puede usar minutos teoricos o suma de estudios de tiempo reales."),
        ("CIF", "CIF incluye costos manuales, depreciacion de activos y planilla MOI."),
        ("Estado de Resultados", "Precio final = costo total + utilidad + IGV configurado."),
    ]
    return render_template("ayuda.html", modulos=modulos)


# ─── Kardex ───────────────────────────────────────────────────────────────────

@app.route("/kardex/<int:ing_id>")
def kardex(ing_id):
    db = g.db
    ingrediente = db.execute("SELECT * FROM ingredientes WHERE id = ?", (ing_id,)).fetchone()
    movimientos = db.execute("SELECT * FROM kardex WHERE ingrediente_id = ? ORDER BY id", (ing_id,)).fetchall()
    last = movimientos[-1] if movimientos else None
    return render_template("kardex.html", ingrediente=ingrediente, movimientos=movimientos, last=last)


@app.route("/kardex/<int:ing_id>/nuevo", methods=["POST"])
def kardex_nuevo(ing_id):
    db = g.db
    fecha = request.form.get("fecha", "2025-01-01")
    tipo = request.form.get("tipo", "ENTRADA")
    cantidad = float(request.form.get("cantidad", 0))
    unidad = request.form.get("unidad", "kg").strip()
    costo_unit = float(request.form.get("costo_unitario", 0))

    last = db.execute("SELECT saldo_cantidad, saldo_valor FROM kardex WHERE ingrediente_id = ? ORDER BY id DESC LIMIT 1", (ing_id,)).fetchone()
    saldo_cant = last["saldo_cantidad"] if last else 0
    saldo_val = last["saldo_valor"] if last else 0

    if tipo == "ENTRADA":
        saldo_cant += cantidad
        saldo_val += cantidad * costo_unit
    elif tipo == "SALIDA":
        saldo_cant = max(0, saldo_cant - cantidad)
        costo_prom = saldo_val / saldo_cant if saldo_cant > 0 else costo_unit
        saldo_val = max(0, saldo_val - cantidad * costo_prom)
    elif tipo == "AJUSTE":
        saldo_cant = cantidad
        saldo_val = cantidad * costo_unit

    costo_total = cantidad * costo_unit
    db.execute(
        "INSERT INTO kardex (ingrediente_id, fecha, tipo, cantidad, unidad, costo_unitario, costo_total, saldo_cantidad, saldo_valor) VALUES (?,?,?,?,?,?,?,?,?)",
        (ing_id, fecha, tipo, cantidad, unidad, costo_unit, costo_total, round(saldo_cant, 4), round(saldo_val, 4))
    )
    db.commit()
    flash("Movimiento registrado.", "success")
    return redirect(url_for("kardex", ing_id=ing_id))


# ─── Estado de Resultados ─────────────────────────────────────────────────────

@app.route("/resultado/<int:plato_id>")
def resultado(plato_id):
    db = g.db
    plato = db.execute("SELECT * FROM platos WHERE id = ?", (plato_id,)).fetchone()
    if not plato:
        flash("Plato no encontrado.", "danger")
        return redirect(url_for("dashboard"))

    utilidad_pct = float(request.args.get("utilidad_pct", 35))

    proj = db.execute("SELECT * FROM proyeccion WHERE plato_id = ?", (plato_id,)).fetchone()
    if not proj:
        flash("No se puede calcular: falta proyección de demanda.", "warning")
        return redirect(url_for("proyeccion"))

    pcts = calcular_pct_participacion(db)
    pct = pcts.get(plato_id, 0)

    er = calcular_estado_resultados(db, plato_id, utilidad_pct)

    prod = db.execute("SELECT * FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()

    return render_template("resultado.html",
                           plato=plato,
                           proj=proj,
                           pct=round(pct * 100, 4),
                           mp=er["mp"], mp_detalle=er["mp_detalle"],
                           mod=er["mod"], costo_min=er["costo_min"], prod=prod,
                           cif=er["cif"], cif_detalle=er["cif_detalle"],
                           ga=er["ga"], ga_detalle=er["ga_detalle"],
                           gv=er["gv"], gv_detalle=er["gv_detalle"],
                           gf=er["gf"], gf_detalle=er["gf_detalle"],
                           costo_produccion=er["costo_produccion"],
                           costo_total=er["costo_total"],
                           utilidad_pct=utilidad_pct,
                           utilidad_s=er["utilidad_s"],
                           valor_venta=er["valor_venta"],
                           igv=er["igv"],
                           igv_pct=er["igv_pct"],
                           precio_final=er["precio_final"],
                           config=er["config"])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, debug=False)
