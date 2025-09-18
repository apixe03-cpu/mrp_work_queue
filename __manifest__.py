{
    "name": "MRP Work Queue",
    "version": "18.0.1.0.0",
    "summary": "Planificador por empleado con kanban doble y 'Siguiente orden'",
    "author": "Tú",
    "license": "LGPL-3",
    "depends": ["mrp", "hr", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/planner_views.xml",
        "views/queue_item_views.xml",
        "wizard/next_workorder_wizard_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_work_queue/static/src/js/dual_kanban.js",
        ],
    },
    "application": True,
}
