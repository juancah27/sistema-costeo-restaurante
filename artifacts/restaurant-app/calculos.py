def _money(value, digits=4):
    """
    Normaliza valores numericos para presentacion monetaria.
    Formula: valor_redondeado = round(valor, digitos).
    Parametros: value numerico y digits cantidad de decimales.
    Retorna: numero float redondeado.
    """
    return round(float(value or 0), digits)


def obtener_configuracion(db):
    """
    Devuelve la configuracion general del sistema.
    Formula: configuracion = pares clave/valor guardados en tabla configuracion.
    Parametros: db conexion SQLite.
    Retorna: dict con nombre_negocio, igv_pct, moneda y sector.
    """
    rows = db.execute("SELECT clave, valor FROM configuracion").fetchall()
    config = {row["clave"]: row["valor"] for row in rows}
    config.setdefault("nombre_negocio", "Mi Restaurante")
    config.setdefault("igv_pct", "10")
    config.setdefault("moneda", "PEN")
    config.setdefault("sector", "RESTAURANTE")
    return config


def convertir_unidad(cantidad, unidad_origen, unidad_destino, rendimiento=None):
    """
    Convierte cantidades entre unidades operativas.
    Formula: g <-> kg y ml <-> litro usan factor 1000; unidad -> g/ml usa rendimiento.
    Parametros: cantidad, unidad_origen, unidad_destino, rendimiento opcional.
    Retorna: cantidad convertida.
    """
    cantidad = float(cantidad or 0)
    origen = (unidad_origen or "").lower()
    destino = (unidad_destino or "").lower()
    if origen == destino:
        return cantidad
    factores = {
        ("kg", "g"): 1000,
        ("g", "kg"): 1 / 1000,
        ("litro", "ml"): 1000,
        ("ml", "litro"): 1 / 1000,
    }
    if (origen, destino) in factores:
        return cantidad * factores[(origen, destino)]
    if origen == "unidad" and destino in ("g", "ml"):
        return cantidad * float(rendimiento or 1)
    if destino == "unidad" and origen in ("g", "ml"):
        return cantidad / float(rendimiento or 1)
    return cantidad


def calcular_depreciacion_mensual(db):
    """
    Calcula depreciacion mensual de activos fijos activos.
    Formula: depreciacion_mensual = (valor_adquisicion - valor_residual) / vida_util_anos / 12.
    Parametros: db conexion SQLite.
    Retorna: total mensual y detalle por activo.
    """
    activos = db.execute("SELECT * FROM activos_fijos WHERE activo = 1").fetchall()
    total = 0
    detalle = []
    for activo in activos:
        dep_anual = (activo["valor_adquisicion"] - activo["valor_residual"]) / activo["vida_util_anos"]
        dep_mensual = dep_anual / 12
        total += dep_mensual
        detalle.append({**dict(activo), "dep_anual": dep_anual, "dep_mensual": dep_mensual})
    return _money(total), detalle


def calcular_pct_participacion(db):
    """
    Calcula participacion de cada plato en la demanda mensual.
    Formula: pct = cantidad_plato / cantidad_total.
    Parametros: db conexion SQLite.
    Retorna: dict plato_id -> porcentaje decimal.
    """
    rows = db.execute("SELECT plato_id, cantidad_mensual FROM proyeccion").fetchall()
    total = sum(row["cantidad_mensual"] for row in rows)
    if total == 0:
        return {}
    return {row["plato_id"]: row["cantidad_mensual"] / total for row in rows}


def calcular_planilla_por_clasificacion(db):
    """
    Agrupa la planilla mensual por clasificacion de empleado.
    Formula: sueldo_total = sueldo_base + gratificaciones + bonificaciones + seguro + cts.
    Parametros: db conexion SQLite.
    Retorna: dict con MOD, MOI, ADMIN, VENTAS y TOTAL.
    """
    result = {"MOD": 0, "MOI": 0, "ADMIN": 0, "VENTAS": 0, "TOTAL": 0}
    rows = db.execute(
        """
        SELECT clasificacion,
               SUM(sueldo_base+gratificaciones+bonificaciones+seguro+cts) AS total
        FROM empleados
        GROUP BY clasificacion
        """
    ).fetchall()
    for row in rows:
        key = row["clasificacion"] or "MOD"
        result[key] = row["total"] or 0
        result["TOTAL"] += row["total"] or 0
    return result


def tiempo_real_por_plato(db, plato_id):
    """
    Suma tiempos observados para un plato.
    Formula: tiempo_total = suma(tiempo_observado).
    Parametros: db conexion SQLite y plato_id.
    Retorna: minutos observados.
    """
    row = db.execute(
        "SELECT SUM(tiempo_observado) AS total FROM estudios_tiempo WHERE plato_id = ?",
        (plato_id,),
    ).fetchone()
    return row["total"] or 0


def mod_por_plato(db, plato_id):
    """
    Calcula mano de obra directa unitaria.
    Formula: MOD = costo_minuto_MOD * minutos_plato; costo_minuto_MOD = planilla_MOD / tiempo_efectivo.
    Parametros: db conexion SQLite y plato_id.
    Retorna: monto MOD, costo por minuto y metadata de tiempo.
    """
    prod = db.execute("SELECT * FROM produccion_empleado WHERE plato_id = ?", (plato_id,)).fetchone()
    if not prod:
        return 0, 0
    planilla_mod = calcular_planilla_por_clasificacion(db)["MOD"]
    tiempo_base = prod["dias_laborables"] * prod["horas_por_dia"] * 60
    tiempo_efectivo = tiempo_base * (prod["productividad"] / 100)
    if tiempo_efectivo == 0:
        return 0, 0
    minutos = tiempo_real_por_plato(db, plato_id) if prod["usar_tiempo_real"] else prod["minutos_por_plato"]
    costo_minuto = planilla_mod / tiempo_efectivo
    return _money(costo_minuto * minutos), _money(costo_minuto, 6)


def mp_por_plato(db, plato_id):
    """
    Calcula materia prima unitaria considerando rendimiento.
    Formula: costo_unitario_real = costo_compra / (equivalencia * rendimiento_pct).
    Parametros: db conexion SQLite y plato_id.
    Retorna: total MP y detalle por ingrediente.
    """
    rows = db.execute(
        """
        SELECT r.cantidad_uso, r.unidad_uso, i.nombre, i.costo_compra, i.unidad_compra,
               i.unidad_medida, i.rendimiento, c.equivalencia, c.factor_conversion
        FROM recetas r
        JOIN ingredientes i ON r.ingrediente_id = i.id
        LEFT JOIN conversiones c ON c.ingrediente_id = i.id
        WHERE r.plato_id = ?
        """,
        (plato_id,),
    ).fetchall()
    total = 0
    detalle = []
    for row in rows:
        equivalencia = row["equivalencia"] or row["factor_conversion"] or 1
        rendimiento = row["rendimiento"] or equivalencia
        rendimiento_pct = rendimiento / equivalencia if equivalencia else 1
        base_util = equivalencia * rendimiento_pct or 1
        costo_unitario_real = row["costo_compra"] / base_util
        cantidad_base = convertir_unidad(row["cantidad_uso"], row["unidad_uso"], "ml" if row["unidad_compra"] == "litro" else "g", rendimiento)
        costo = costo_unitario_real * cantidad_base
        total += costo
        detalle.append(
            {
                "ingrediente": row["nombre"],
                "cantidad_uso": row["cantidad_uso"],
                "unidad_uso": row["unidad_uso"],
                "costo_compra": row["costo_compra"],
                "unidad_compra": row["unidad_compra"],
                "rendimiento": rendimiento,
                "rendimiento_pct": rendimiento_pct * 100,
                "costo_unitario_real": costo_unitario_real,
                "costo_total": _money(costo),
            }
        )
    return _money(total), detalle


def depreciacion_por_plato(db, pct, cantidad_mensual):
    """
    Distribuye depreciacion mensual a costo unitario.
    Formula: dep_unitaria = (depreciacion_total * pct) / cantidad_mensual.
    Parametros: db, pct decimal, cantidad mensual.
    Retorna: depreciacion por unidad.
    """
    total_dep, _ = calcular_depreciacion_mensual(db)
    if cantidad_mensual == 0:
        return 0
    return _money((total_dep * pct) / cantidad_mensual)


def cif_por_plato(db, plato_id):
    """
    Calcula CIF unitario incluyendo conceptos, depreciacion y MOI.
    Formula: valor_plato = (monto * pct) / cantidad; CIF = suma(valor_plato).
    Parametros: db conexion SQLite y plato_id.
    Retorna: total CIF y detalle.
    """
    pcts = calcular_pct_participacion(db)
    pct = pcts.get(plato_id, 0)
    row = db.execute("SELECT cantidad_mensual FROM proyeccion WHERE plato_id = ?", (plato_id,)).fetchone()
    if not row or row["cantidad_mensual"] == 0:
        return 0, []
    cantidad = row["cantidad_mensual"]
    detalle = []
    total = 0
    for item in db.execute("SELECT * FROM costos_indirectos").fetchall():
        valor = (item["monto"] * pct) / cantidad
        total += valor
        detalle.append({**dict(item), "valor_plato": _money(valor), "automatico": 0})
    dep = depreciacion_por_plato(db, pct, cantidad)
    total += dep
    detalle.append({"concepto": "Depreciacion activos", "monto": None, "categoria": "GENERAL", "prioridad": 0, "valor_plato": dep, "automatico": 1})
    planilla_moi = calcular_planilla_por_clasificacion(db)["MOI"]
    moi_unit = (planilla_moi * pct) / cantidad
    total += moi_unit
    detalle.append({"concepto": "Planilla MOI", "monto": planilla_moi, "categoria": "GENERAL", "prioridad": 0, "valor_plato": _money(moi_unit), "automatico": 1})
    return _money(total), detalle


def gastos_por_plato(db, tabla, plato_id):
    """
    Calcula gastos unitarios por tabla, incluyendo planillas automaticas cuando aplica.
    Formula: gasto_unitario = (monto * pct) / cantidad.
    Parametros: db, tabla de gasto y plato_id.
    Retorna: total unitario y detalle.
    """
    pcts = calcular_pct_participacion(db)
    pct = pcts.get(plato_id, 0)
    row = db.execute("SELECT cantidad_mensual FROM proyeccion WHERE plato_id = ?", (plato_id,)).fetchone()
    if not row or row["cantidad_mensual"] == 0:
        return 0, []
    cantidad = row["cantidad_mensual"]
    detalle = []
    total = 0
    for item in db.execute(f"SELECT * FROM {tabla}").fetchall():
        valor = (item["monto"] * pct) / cantidad
        total += valor
        detalle.append({**dict(item), "valor_plato": _money(valor), "automatico": 0})
    automaticos = []
    planillas = calcular_planilla_por_clasificacion(db)
    if tabla == "gastos_admin":
        automaticos.append(("Planilla personal ADMIN", planillas["ADMIN"], "GENERAL"))
    elif tabla == "gastos_ventas":
        automaticos.append(("Planilla personal VENTAS", planillas["VENTAS"], "GENERAL"))
    for concepto, monto, categoria in automaticos:
        valor = (monto * pct) / cantidad
        total += valor
        detalle.append({"concepto": concepto, "monto": monto, "categoria": categoria, "valor_plato": _money(valor), "automatico": 1})
    return _money(total), detalle


def calcular_estado_resultados(db, plato_id, utilidad_pct=35):
    """
    Calcula el estado de resultados unitario completo.
    Formula: precio_final = costo_total + utilidad + IGV.
    Parametros: db, plato_id y utilidad_pct.
    Retorna: dict con totales y detalles.
    """
    config = obtener_configuracion(db)
    igv_pct = float(config.get("igv_pct", 10) or 10)
    mp, mp_detalle = mp_por_plato(db, plato_id)
    mod, costo_min = mod_por_plato(db, plato_id)
    cif, cif_detalle = cif_por_plato(db, plato_id)
    ga, ga_detalle = gastos_por_plato(db, "gastos_admin", plato_id)
    gv, gv_detalle = gastos_por_plato(db, "gastos_ventas", plato_id)
    gf, gf_detalle = gastos_por_plato(db, "gastos_financieros", plato_id)
    costo_produccion = _money(mp + mod + cif)
    costo_total = _money(costo_produccion + ga + gv + gf)
    utilidad_s = _money(costo_total * (float(utilidad_pct) / 100))
    valor_venta = _money(costo_total + utilidad_s)
    igv = _money(valor_venta * (igv_pct / 100))
    precio_final = _money(valor_venta + igv)
    return {
        "config": config,
        "igv_pct": igv_pct,
        "mp": mp, "mp_detalle": mp_detalle,
        "mod": mod, "costo_min": costo_min,
        "cif": cif, "cif_detalle": cif_detalle,
        "ga": ga, "ga_detalle": ga_detalle,
        "gv": gv, "gv_detalle": gv_detalle,
        "gf": gf, "gf_detalle": gf_detalle,
        "costo_produccion": costo_produccion,
        "costo_total": costo_total,
        "utilidad_s": utilidad_s,
        "valor_venta": valor_venta,
        "igv": igv,
        "precio_final": precio_final,
    }
