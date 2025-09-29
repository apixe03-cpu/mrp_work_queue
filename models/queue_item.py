# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class WorkQueueItem(models.Model):
    _name = "work.queue.item"
    _description = "Work Queue Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    workorder_id = fields.Many2one(
        "mrp.workorder",
        required=True,
        ondelete="cascade",
        index=True,
        string="Workorder",
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        store=True,
        index=True,
        readonly=True,
        string="Work Center",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        store=False,
        readonly=True,
        string="Manufacturing Order",
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        store=False,
        readonly=True,
        string="Product",
    )
    state = fields.Selection(
        related="workorder_id.state",
        store=False,
        readonly=True,
        string="Status",
    )

    # Asignación
    employee_id = fields.Many2one("hr.employee", index=True, string="Employee")
    plan_id = fields.Many2one("work.queue.plan", index=True, string="Plan")
    # Helper para mostrar el backlog de este plan en la columna izquierda
    plan_backlog_helper_id = fields.Many2one("work.queue.plan", index=True, string="Plan Backlog Helper")

    _sql_constraints = [
        ("uniq_workorder", "unique(workorder_id)", "Cada orden de trabajo puede estar en una sola cola."),
    ]

    # ---------- Acciones desde la vista ----------
    def action_assign_to_employee(self):
        """ Botón →: asigna este ítem al empleado del plan activo. """
        plan = self.env["work.queue.plan"].browse(self.env.context.get("active_id"))
        if not plan:
            return
        for rec in self:
            rec.write({
                "employee_id": plan.employee_id.id,
                "plan_id": plan.id,
                "plan_backlog_helper_id": False,  # ya no está en backlog
            })
        return True

    def action_unassign(self):
        """ Botón ←: devuelve a backlog del plan activo (sin empleado). """
        plan = self.env["work.queue.plan"].browse(self.env.context.get("active_id"))
        for rec in self:
            rec.write({
                "employee_id": False,
                "plan_id": False,
                "plan_backlog_helper_id": plan.id if plan else False,
            })
        return True
