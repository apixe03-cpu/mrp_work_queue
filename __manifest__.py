{
    "name": "MRP Work Queue (Admin Planner + Next Order)",
    "version": "18.0.1.0.0",
    "summary": "Planificador por empleado con prioridad drag-and-drop y botón 'Siguiente orden' para planta",
    "author": "ChatGPT helper",
    "license": "LGPL-3",
    "depends": ["mrp", "hr"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",

        "views/queue_item_views.xml",
        "views/planner_views.xml",                 # <- define action_work_queue_plan_by_wc
        "wizard/next_workorder_wizard_views.xml",  # <- define action_next_workorder_wizard

        "views/menu.xml"                           # <- SIEMPRE AL FINAL
    ],
    "application": True
}
