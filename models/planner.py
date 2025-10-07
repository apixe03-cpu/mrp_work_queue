# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

AVAILABLE_STATES = ("ready", "pending", "progress")

class WorkQueuePlan(models.Model):
    _name = "work.queue.plan"
    _description = "Planificador por empleado"

    workcenter_id = fields.Many2one("mrp.workcenter", required=True, string="Workcenter", index=True)
    employee_id   = fields.Many2one("hr.employee",   required=True, string="Employee",   index=True)
    company_id    = fields.Many2one("res.company", default=lambda s: s.env.company, string="Company", index=True)

    line_ids = fields.One2many("work.queue.item", "plan_id", string="")
    backlog_item_ids = fields.One2many("work.queue.item", "plan_backlog_helper_id", string="")
    line_count = fields.Integer(string="En cola", compute="_compute_line_count", store=False)

    _sql_constraints = [
        # 1 sola cola por (Centro, Empleado, Compañía)
        (
            "uniq_wc_emp_company",
            "unique(workcenter_id, employee_id, company_id)",
            "Ya existe una cola para este Centro de trabajo y Empleado en esta compañía."
        ),
    ]

    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def _clean_backlog(self):
        for plan in self:
            plan.backlog_item_ids.unlink()

    def action_load_available(self):
        for plan in self:
            if not plan.workcenter_id:
                raise UserError(_("Seleccione un Centro de trabajo."))
            plan._clean_backlog()
            QueueItem = self.env["work.queue.item"]
            Workorder = self.env["mrp.workorder"]
            wo_domain = [
                ("workcenter_id", "=", plan.workcenter_id.id),
                ("state", "in", AVAILABLE_STATES),
            ]
            workorders = Workorder.search(wo_domain)
            existing_items = QueueItem.search([("workorder_id", "in", workorders.ids)])
            by_wo = {it.workorder_id.id: it for it in existing_items}
            for wo in workorders:
                item = by_wo.get(wo.id)
                if item:
                    if not item.employee_id:
                        item.write({"plan_backlog_helper_id": plan.id})
                    continue
                QueueItem.create({
                    "workorder_id": wo.id,
                    "plan_backlog_helper_id": plan.id,
                })
        return True
