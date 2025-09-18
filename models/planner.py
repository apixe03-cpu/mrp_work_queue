from odoo import api, fields, models

class WorkQueuePlan(models.Model):
    _name = "work.queue.plan"
    _description = "Work Queue Plan"

    workcenter_id = fields.Many2one("mrp.workcenter", required=True)
    employee_id = fields.Many2one("hr.employee", required=True)

    # Cola del empleado (derecha): ítems del empleado y del centro en este plan
    line_ids = fields.One2many(
        "work.queue.item",
        "plan_id",
        domain="[('employee_id', '=', employee_id), ('workcenter_id', '=', workcenter_id)]",
        string="Cola del empleado",
    )

    # Backlog (izquierda): todos los items del centro (asignados o no) enganchados a ESTE plan
    backlog_item_ids = fields.One2many(
        "work.queue.item",
        "plan_backlog_helper_id",
        string="Backlog",
        readonly=True,
    )

    def action_load_available(self):
        """Crea items para todas las mrp.workorder del centro (si no existen)
        y engancha su backlog a ESTE plan (sin duplicar).
        """
        self.ensure_one()
        WQI = self.env["work.queue.item"]

        # 1) Workorders del centro en estados relevantes
        wos = self.env["mrp.workorder"].search([
            ("workcenter_id", "=", self.workcenter_id.id),
            ("state", "in", ["pending", "ready", "progress"]),
        ])

        # 2) Crear items que no existan (único por workorder)
        existing = WQI.search([("workorder_id", "in", wos.ids)])
        existing_by_wo = set(existing.mapped("workorder_id").ids)

        vals_list = []
        for wo in wos:
            if wo.id not in existing_by_wo:
                vals_list.append({"workorder_id": wo.id})
        if vals_list:
            WQI.create(vals_list)

        # 3) Recalcular backlog para este plan (enganche visual)
        all_items = WQI.search([("workorder_id", "in", wos.ids)])
        all_items.write({"plan_backlog_helper_id": self.id})

        return True
