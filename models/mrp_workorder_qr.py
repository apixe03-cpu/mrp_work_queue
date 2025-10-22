# -*- coding: utf-8 -*-
import base64
import io
from odoo import api, fields, models

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except Exception:
    qrcode = None


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # No almacenado: se calcula siempre que el reporte lo pida
    qr_code = fields.Binary(string="QR Code", compute="_compute_qr_code", compute_sudo=True, store=False)
    qr_text = fields.Char(string="QR text", compute="_compute_qr_text", store=False)

    def _qr_payload(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        return f"{base}/wo/{self.id}"

    def _compute_qr_text(self):
        for wo in self:
            wo.qr_text = wo._qr_payload()

    @api.depends("name", "product_id", "production_id", "state")
    def _compute_qr_code(self):
        for wo in self:
            if not qrcode:
                wo.qr_code = False
                continue
            payload = wo._qr_payload()
            qr = qrcode.QRCode(
                version=None,
                error_correction=ERROR_CORRECT_M,
                box_size=6,
                border=2,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            wo.qr_code = base64.b64encode(buf.getvalue())
    
    def action_finish_from_qr(self):
        """Registra scrap (si corresponde) y finaliza la WO.
           Estrategia:
           - Si qty_scrap > 0: creamos stock.scrap ligado a la MO.
           - Si qty_good > 0: dejamos que Odoo consuma y termine la WO.
        """
        self.ensure_one()
        qty_good = float(self.env.context.get('qty_good') or 0.0)
        qty_scrap = float(self.env.context.get('qty_scrap') or 0.0)

        # 1) Scrap (descartar sin sumar a producto terminado)
        if qty_scrap > 0:
            Scrap = self.env['stock.scrap'].sudo()
            # Tomamos el producto de salida de la MO (no siempre coincide con self.product_id cuando hay varias ops).
            finished_prod = self.production_id.product_id
            Scrap.create({
                'product_id': finished_prod.id,
                'scrap_qty': qty_scrap,
                'uom_id': finished_prod.uom_id.id,
                'company_id': self.company_id.id,
                'production_id': self.production_id.id,
                'location_id': self.production_id.location_src_id.id,
            }).action_validate()

        # 2) Finalizar la WO (Odoo se encarga del consumo; si hay múltiples operaciones, respeta la secuencia)
        #    Si querés forzar qty_good a moverse como producido parcial, podés usar el asistente de producción.
        #    Como simplificación, si qty_good == 0, igualmente se cierra la WO (p.ej. operación de control).
        self.button_finish()

        # 3) Si querés producir parcialmente qty_good a nivel MO en vez de solo terminar la WO:
        #    descomentar esta parte en instalaciones donde haga falta:
        # if qty_good > 0:
        #     self.production_id._record_production(qty_good)  # método existe según versión; si no, usamos wizard
