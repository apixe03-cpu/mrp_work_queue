# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

AVAILABLE_STATES = ("ready", "pending", "progress")


class WorkQueuePlan(models.Model):
    _name = "work.queue.plan"
    _description = "Planificador por empleado"

    workcenter_id = fields.Many2one(
        "mrp.workcenter", required=True, index=True, string="Workcenter"
    )
    employee_id = fields.Many2one(
        "hr.employee", required=True, index=True, string="Employee"
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company, index=True, string="Company"
    )

    line_ids = fields.One2many("work.queue.item", "plan_id", string="")
    backlog_item_ids = fields.One2many("work.queue.item", "plan_backlog_helper_id", string="")
    line_count = fields.Integer(string="En cola", compute="_compute_line_count", store=False)

    _sql_constraints = [
        (
            "uniq_wc_emp_company",
            "unique(workcenter_id, employee_id, company_id)",
            "Ya existe una cola para este Centro de trabajo y Empleado en esta compañía."
        ),
    ]

    @api.constrains('workcenter_id', 'employee_id', 'company_id')
    def _check_unique_combo(self):
        for rec in self:
            if not (rec.workcenter_id and rec.employee_id and rec.company_id):
                continue
            domain = [
                ('workcenter_id', '=', rec.workcenter_id.id),
                ('employee_id',   '=', rec.employee_id.id),
                ('company_id',    '=', rec.company_id.id),
                ('id',            '!=', rec.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_("Ya existe una cola para este Centro de trabajo y Empleado en esta compañía."))

    @api.depends('line_ids')
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

            QueueItem = self.env["work.queue.item"].sudo()
            Workorder = self.env["mrp.workorder"].sudo()

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
