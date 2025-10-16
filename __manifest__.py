# -*- coding: utf-8 -*-
{
    "name": "MRP Work Queue",
    "summary": "Planificador por empleado: asignar y priorizar órdenes de trabajo",
    "version": "18.0.1.0",
    "category": "Manufacturing/Manufacturing",
    "license": "LGPL-3",
    "author": "You",
    "depends": ["mrp", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/planner_views.xml",
        "views/menu.xml",
        "views/report_workorder_80mm.xml",
    ],
    "post_init_hook": "post_init_hook",
    "assets": {
    "web.assets_backend": [
        "mrp_work_queue/static/src/css/queue.css",
        ],
    },
    "installable": True,
    "application": False,
}