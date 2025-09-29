# -*- coding: utf-8 -*-
{
    "name": "MRP Work Queue",
    "summary": "Planificador por empleado: asignar y priorizar órdenes de trabajo",
    "version": "18.0.1.0",
    "category": "Manufacturing",
    "license": "LGPL-3",
    "author": "You",
    "depends": ["mrp", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/queue_item_views.xml",
        "views/planner_views.xml",
        "views/menu.xml",
    ],
    # MUY IMPORTANTE: sin assets JS para evitar pantallas blancas
    "assets": {},
    "installable": True,
    "application": False,
}
