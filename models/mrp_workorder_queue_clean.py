# -*- coding: utf-8 -*-
from odoo import api, models

class MrpWorkorderQueueClean(models.Model):
    _inherit = 'mrp.workorder'

    def write(self, vals):
        res = super().write(vals)

        # Si alguna WO pasó a done o cancel, borramos su item de la cola.
        if 'state' in vals:
            done_or_cancel = self.filtered(lambda w: w.state in ('done', 'cancel'))
            if done_or_cancel:
                items = self.env['work.queue.item'].sudo().search([
                    ('workorder_id', 'in', done_or_cancel.ids)
                ])
                # Eliminar de cualquier cola (line_ids o backlog)
                if items:
                    items.unlink()
        return res
