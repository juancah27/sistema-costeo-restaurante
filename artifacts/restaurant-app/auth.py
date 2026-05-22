from functools import wraps

from flask import redirect, render_template, request, session, url_for


PERMISOS = {
    "ADMIN": {"todos": "total"},
    "GERENTE": {
        "platos": "total",
        "ingredientes": "total",
        "conversiones": "total",
        "recetas": "total",
        "proyeccion": "total",
        "empleados": "total",
        "productividad": "total",
        "estudios_tiempo": "total",
        "cif": "total",
        "activos": "total",
        "gastos_admin": "total",
        "gastos_ventas": "total",
        "gastos_financieros": "total",
        "kardex": "total",
        "resultado": "total",
        "dashboard": "total",
        "manuales": "total",
    },
    "CONTADOR": {
        "platos": "lectura",
        "ingredientes": "lectura",
        "conversiones": "lectura",
        "recetas": "lectura",
        "proyeccion": "total",
        "empleados": "total",
        "productividad": "lectura",
        "estudios_tiempo": "lectura",
        "cif": "total",
        "activos": "total",
        "gastos_admin": "total",
        "gastos_ventas": "total",
        "gastos_financieros": "total",
        "kardex": "lectura",
        "resultado": "total",
        "dashboard": "total",
        "manuales": "total",
    },
    "COCINA": {
        "platos": "total",
        "ingredientes": "total",
        "conversiones": "total",
        "recetas": "total",
        "productividad": "total",
        "estudios_tiempo": "total",
        "kardex": "total",
        "resultado": "lectura",
        "dashboard": "total",
        "manuales": "total",
    },
    "CONSULTA": {
        "platos": "lectura",
        "ingredientes": "lectura",
        "conversiones": "lectura",
        "recetas": "lectura",
        "proyeccion": "lectura",
        "empleados": "lectura",
        "productividad": "lectura",
        "estudios_tiempo": "lectura",
        "cif": "lectura",
        "activos": "lectura",
        "gastos_admin": "lectura",
        "gastos_ventas": "lectura",
        "gastos_financieros": "lectura",
        "kardex": "lectura",
        "resultado": "lectura",
        "dashboard": "lectura",
        "manuales": "total",
    },
}

ACCION_A_NIVEL = {
    "ver": "lectura",
    "crear": "total",
    "editar": "total",
    "eliminar": "total",
}


def nivel_permiso(rol, modulo):
    permisos_rol = PERMISOS.get(rol, {})
    if permisos_rol.get("todos") == "total":
        return "total"
    return permisos_rol.get(modulo)


def verificar_permiso(rol, modulo, accion):
    nivel = nivel_permiso(rol, modulo)
    if not nivel:
        return False
    if nivel == "total":
        return True
    return nivel == "lectura" and accion == "ver"


def tiene_permiso(rol, modulo, nivel_requerido="lectura"):
    accion = "ver" if nivel_requerido == "lectura" else "editar"
    return verificar_permiso(rol, modulo, accion)


def login_requerido(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return func(*args, **kwargs)

    return wrapper


def permiso_requerido(modulo, nivel="lectura"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not tiene_permiso(session.get("rol"), modulo, nivel):
                return render_template("403.html"), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator
