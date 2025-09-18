{
    "name": "MRP Work Queue (Admin Planner + Next Order)",
    "version": "18.0.1.0.0",
    "summary": "Planificador por empleado con kanban doble y botón 'Siguiente orden' en planta",
    "author": "Tu equipo",
    "license": "LGPL-3",
    "depends": ["mrp", "hr", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/queue_item_views.xml",              # si ya lo tenés, dejalo
        "views/planner_views.xml",                 # ← este lo actualizamos
        "wizard/next_workorder_wizard_views.xml",  # si ya lo tenés, dejalo
        "views/menu.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_work_queue/static/src/js/dual_kanban.js",
        ],
    },
    "application": True,
}
