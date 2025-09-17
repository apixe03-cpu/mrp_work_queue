
from odoo import models

class MrpWorkorderHooks(models.Model):
    _inherit = "mrp.workorder"

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals and vals.get("state") == "done":
            items = self.env["work.queue.item"].search([("workorder_id", "in", self.ids)])
            items.unlink()
        return res
