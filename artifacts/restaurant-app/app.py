from flask import Flask, render_template, request, redirect, url_for, flash, g
import os
from database import (
    get_db, init_db,
    calcular_depreciacion_mensual, calcular_pct_participacion,
    cif_por_plato, mod_por_plato, mp_por_plato, gastos_por_plato
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "restaurant-secret-2025")

PORT = int(os.environ.get("PORT", 5001))


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
    items = db.execute("SELECT * FROM ingredientes ORDER BY nombre").fetchall()
    return render_template("ingredientes.html", ingredientes=items)


@app.route("/ingredientes/nuevo", methods=["POST"])
def ingrediente_nuevo():
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    costo = float(request.form.get("costo_compra", 0))
    unidad = request.form.get("unidad_compra", "kg").strip()
    equiv = float(request.form.get("equivalencia", 1000))
    unidad_uso = request.form.get("unidad_uso", "g").strip()
    if nombre:
        cur = db.execute("INSERT INTO ingredientes (nombre, costo_compra, unidad_compra) VALUES (?,?,?)",
                         (nombre, costo, unidad))
        db.execute("INSERT INTO conversiones (ingrediente_id, equivalencia, unidad_uso) VALUES (?,?,?)",
                   (cur.lastrowid, equiv, unidad_uso))
        db.commit()
        flash("Ingrediente creado.", "success")
    return redirect(url_for("ingredientes"))


@app.route("/ingredientes/editar/<int:iid>", methods=["POST"])
def ingrediente_editar(iid):
    db = g.db
    nombre = request.form.get("nombre", "").strip()
    costo = float(request.form.get("costo_compra", 0))
    unidad = request.form.get("unidad_compra", "kg").strip()
    db.execute("UPDATE ingredientes SET nombre=?, costo_compra=?, unidad_compra=? WHERE id=?",
               (nombre, costo, unidad, iid))
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
    return render_template("empleados.html", empleados=items, planilla_total=planilla_total)


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
    if nombre:
        db.execute("INSERT INTO empleados (nombre, cargo, sueldo_base, gratificaciones, bonificaciones, seguro, cts) VALUES (?,?,?,?,?,?,?)",
                   (nombre, cargo, sueldo_base, gratif, bonif, seguro, cts))
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
    db.execute("UPDATE empleados SET nombre=?, cargo=?, sueldo_base=?, gratificaciones=?, bonificaciones=?, seguro=?, cts=? WHERE id=?",
               (nombre, cargo, sueldo_base, gratif, bonif, seguro, cts, eid))
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
    planilla_total = db.execute(
        "SELECT SUM(sueldo_base+gratificaciones+bonificaciones+seguro+cts) AS total FROM empleados"
    ).fetchone()["total"] or 0
    mod_data = []
    for p in platos:
        pr = prod_map.get(p["id"])
        mod, costo_min = mod_por_plato(db, p["id"])
        mod_data.append({"plato": p, "prod": pr, "mod": mod, "costo_min": costo_min})
    return render_template("productividad.html", platos=platos, prod_map=prod_map,
                           planilla_total=planilla_total, mod_data=mod_data)


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
            db.execute("UPDATE produccion_empleado SET minutos_por_plato=?, dias_laborables=?, horas_por_dia=?, productividad=? WHERE plato_id=?",
                       (minutos, dias, horas, prod_val, pid))
        else:
            db.execute("INSERT INTO produccion_empleado (plato_id, minutos_por_plato, dias_laborables, horas_por_dia, productividad) VALUES (?,?,?,?,?)",
                       (pid, minutos, dias, horas, prod_val))
    db.commit()
    flash("Parámetros de productividad guardados.", "success")
    return redirect(url_for("productividad"))


# ─── CIF ──────────────────────────────────────────────────────────────────────

@app.route("/costos-indirectos")
def costos_indirectos():
    db = g.db
    items = db.execute("SELECT * FROM costos_indirectos").fetchall()
    total = sum(i["monto"] for i in items)
    return render_template("costos_indirectos.html", items=items, total=total)


@app.route("/costos-indirectos/nuevo", methods=["POST"])
def cif_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    if concepto:
        db.execute("INSERT INTO costos_indirectos (concepto, monto) VALUES (?,?)", (concepto, monto))
        db.commit()
        flash("CIF agregado.", "success")
    return redirect(url_for("costos_indirectos"))


@app.route("/costos-indirectos/editar/<int:cid>", methods=["POST"])
def cif_editar(cid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    db.execute("UPDATE costos_indirectos SET concepto=?, monto=? WHERE id=?", (concepto, monto, cid))
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
    items = db.execute("SELECT * FROM gastos_admin").fetchall()
    total = sum(i["monto"] for i in items)
    return render_template("gastos_admin.html", items=items, total=total)


@app.route("/gastos-admin/nuevo", methods=["POST"])
def ga_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    if concepto:
        db.execute("INSERT INTO gastos_admin (concepto, monto) VALUES (?,?)", (concepto, monto))
        db.commit()
        flash("Gasto administrativo agregado.", "success")
    return redirect(url_for("gastos_admin"))


@app.route("/gastos-admin/editar/<int:gid>", methods=["POST"])
def ga_editar(gid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    db.execute("UPDATE gastos_admin SET concepto=?, monto=? WHERE id=?", (concepto, monto, gid))
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
    items = db.execute("SELECT * FROM gastos_ventas").fetchall()
    total = sum(i["monto"] for i in items)
    return render_template("gastos_ventas.html", items=items, total=total)


@app.route("/gastos-ventas/nuevo", methods=["POST"])
def gv_nuevo():
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    if concepto:
        db.execute("INSERT INTO gastos_ventas (concepto, monto) VALUES (?,?)", (concepto, monto))
        db.commit()
        flash("Gasto de ventas agregado.", "success")
    return redirect(url_for("gastos_ventas"))


@app.route("/gastos-ventas/editar/<int:gid>", methods=["POST"])
def gv_editar(gid):
    db = g.db
    concepto = request.form.get("concepto", "").strip()
    monto = float(request.form.get("monto", 0))
    db.execute("UPDATE gastos_ventas SET concepto=?, monto=? WHERE id=?", (concepto, monto, gid))
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

    mp, mp_detalle = mp_por_plato(db, plato_id)
    mod, costo_min = mod_por_plato(db, plato_id)
    cif, cif_detalle = cif_por_plato(db, plato_id)
    ga, ga_detalle = gastos_por_plato(db, "gastos_admin", plato_id)
    gv, gv_detalle = gastos_por_plato(db, "gastos_ventas", plato_id)
    gf, gf_detalle = gastos_por_plato(db, "gastos_financieros", plato_id)

    costo_produccion = round(mp + mod + cif, 4)
    costo_total = round(costo_produccion + ga + gv + gf, 4)
    utilidad_s = round(costo_total * (utilidad_pct / 100), 4)
    valor_venta = round(costo_total + utilidad_s, 4)
    igv = round(valor_venta * 0.10, 4)
    precio_final = round(valor_venta * 1.10, 4)

    prod = db.execute("SELECT * FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()

    return render_template("resultado.html",
                           plato=plato,
                           proj=proj,
                           pct=round(pct * 100, 4),
                           mp=mp, mp_detalle=mp_detalle,
                           mod=mod, costo_min=costo_min, prod=prod,
                           cif=cif, cif_detalle=cif_detalle,
                           ga=ga, ga_detalle=ga_detalle,
                           gv=gv, gv_detalle=gv_detalle,
                           gf=gf, gf_detalle=gf_detalle,
                           costo_produccion=costo_produccion,
                           costo_total=costo_total,
                           utilidad_pct=utilidad_pct,
                           utilidad_s=utilidad_s,
                           valor_venta=valor_venta,
                           igv=igv,
                           precio_final=precio_final)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, debug=False)
